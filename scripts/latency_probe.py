#!/usr/bin/env python3
"""
MentorForge live-turn latency probe.

Measures end-to-end latency for the Priya first-day turn (EX Story 1) over the
live WebSocket. Reports cold and warm run timings with a breakdown of each segment.

Usage:
    python scripts/latency_probe.py \
        --pool-id   <UserPoolId from cdk deploy outputs> \
        --client-id <UserPoolClientId from cdk deploy outputs> \
        --username  <your-demo-username> \
        --password  <your-demo-password> \
        --wss-url   <WssUrl from cdk deploy outputs> \
        --runs 2

Segments measured (all in ms):
  - conn_ms           : WS TCP handshake time
  - t_thinking_ms     : T0 (sendMessage) → first signal received (thinking)
  - t_first_token_ms  : T0 → first token signal  (AgentCore invocation + Bedrock TTFT)
  - t_first_tool_ms   : T0 → first tool_start chip
  - bedrock_r1_ms     : T0 → first token  (same as t_first_token — the first Bedrock round)
  - bedrock_rN_ms     : last tool_end → last token before HITL/done (final Bedrock round)
  - tool_latencies    : per-tool server-side latency from tool_end.data.latency_ms
  - wire_tool_ms      : client-observed tool_start→tool_end minus server latency_ms (≈ wire RTT)
  - t_hitl_ms         : T0 → awaiting_confirmation (if reached)
  - t_done_ms         : T0 → done/error (full turn)

Outputs a human-readable table per run, then a summary comparison.
"""

import argparse
import asyncio
import json
import os
import sys
import time

import boto3
import websockets

WSS_URL   = os.environ.get("MENTORFORGE_WSS_URL", "")
POOL_ID   = os.environ.get("MENTORFORGE_COGNITO_POOL_ID", "")
CLIENT_ID = os.environ.get("MENTORFORGE_COGNITO_CLIENT_ID", "")
USERNAME  = os.environ.get("MENTORFORGE_DEMO_USERNAME", "")
PASSWORD  = os.environ.get("MENTORFORGE_DEMO_PASSWORD", "")

PRIYA_TURN = (
    "Hi! I'm Priya Nair, starting today at Northstar Consulting on the Atlas-Health engagement. "
    "Can you help me figure out who I should meet first and what I should read to get up to speed?"
)


def get_jwt(pool_id, client_id, username, password):
    import subprocess
    result = subprocess.run(
        ["aws", "cognito-idp", "initiate-auth",
         "--client-id", client_id,
         "--auth-flow", "USER_PASSWORD_AUTH",
         "--auth-parameters", f"USERNAME={username},PASSWORD={password}",
         "--query", "AuthenticationResult.IdToken",
         "--output", "text"],
        capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


async def run_timed_turn(wss_url, token, label, verbose=False):
    """Run one full turn, return a timing dict."""
    url = f"{wss_url}?token={token}"

    t_connect_start = time.perf_counter()
    async with websockets.connect(url) as ws:
        t_connected = time.perf_counter()
        conn_ms = (t_connected - t_connect_start) * 1000

        turn_msg = json.dumps({
            "action": "sendMessage",
            "payload": {"message": PRIYA_TURN},
        })
        t0 = time.perf_counter()
        await ws.send(turn_msg)

        timing = {
            "label": label,
            "conn_ms": conn_ms,
            "t_thinking_ms": None,
            "t_first_token_ms": None,
            "t_first_tool_start_ms": None,
            "t_hitl_ms": None,
            "t_done_ms": None,
            "tool_rounds": [],       # list of {tool, server_ms, client_ms, wire_ms}
            "bedrock_r1_ms": None,   # T0 → first token
            "final_bedrock_ms": None,# last tool_end → last token before HITL
            "signal_log": [],        # [(elapsed_ms, type, brief)]
            "terminal": None,
        }

        last_tool_end_t = None
        last_token_t    = None
        pending_action_id = None
        current_tool_start_t = None
        current_tool_name    = None

        deadline = time.perf_counter() + 240  # 4 min hard cap

        async for raw in ws:
            t_recv = time.perf_counter()
            elapsed_ms = (t_recv - t0) * 1000

            try:
                sig = json.loads(raw)
            except json.JSONDecodeError:
                continue

            stype = sig.get("type", "?")
            data  = sig.get("data", {})

            # brief for log
            brief = ""
            if stype == "token":
                brief = repr(data.get("text", "")[:20])
            elif stype in ("tool_start", "tool_end"):
                brief = data.get("tool", "")
                if stype == "tool_end":
                    brief += f" latency_ms={data.get('latency_ms', '?')}"
            elif stype == "awaiting_confirmation":
                brief = data.get("prompt", "")[:40]

            timing["signal_log"].append((round(elapsed_ms, 1), stype, brief))

            if verbose:
                print(f"  [{elapsed_ms:8.1f}ms] {stype:26s} {brief}")

            # Timing captures
            if stype == "thinking" and timing["t_thinking_ms"] is None:
                timing["t_thinking_ms"] = elapsed_ms

            elif stype == "token":
                if timing["t_first_token_ms"] is None:
                    timing["t_first_token_ms"] = elapsed_ms
                    timing["bedrock_r1_ms"]    = elapsed_ms
                last_token_t = t_recv

            elif stype == "tool_start":
                if timing["t_first_tool_start_ms"] is None:
                    timing["t_first_tool_start_ms"] = elapsed_ms
                current_tool_start_t = t_recv
                current_tool_name    = data.get("tool", "?")

            elif stype == "tool_end":
                server_ms = data.get("latency_ms", 0)
                if current_tool_start_t is not None:
                    client_ms = (t_recv - current_tool_start_t) * 1000
                    wire_ms   = max(0, client_ms - server_ms)
                else:
                    client_ms = wire_ms = None
                timing["tool_rounds"].append({
                    "tool":      current_tool_name or data.get("tool", "?"),
                    "server_ms": server_ms,
                    "client_ms": round(client_ms, 1) if client_ms is not None else None,
                    "wire_ms":   round(wire_ms, 1)   if wire_ms   is not None else None,
                })
                last_tool_end_t      = t_recv
                current_tool_start_t = None
                current_tool_name    = None

            elif stype == "awaiting_confirmation":
                timing["t_hitl_ms"] = elapsed_ms
                if last_tool_end_t and last_token_t:
                    timing["final_bedrock_ms"] = (last_token_t - last_tool_end_t) * 1000
                pending_action_id = data.get("action_id") or (data.get("action") or {}).get("action_id")
                # Auto-confirm so we see action_done + done
                confirm = json.dumps({
                    "action": "confirm",
                    "payload": {"action_id": pending_action_id},
                })
                await ws.send(confirm)
                if verbose:
                    print(f"  [auto-confirm sent]")

            elif stype == "done":
                timing["t_done_ms"]  = elapsed_ms
                timing["terminal"]   = "done"
                if last_tool_end_t and last_token_t and timing["final_bedrock_ms"] is None:
                    timing["final_bedrock_ms"] = (last_token_t - last_tool_end_t) * 1000
                break

            elif stype == "error":
                timing["t_done_ms"] = elapsed_ms
                timing["terminal"]  = f"error: {data.get('message', '')[:60]}"
                break

            if time.perf_counter() > deadline:
                timing["terminal"] = "TIMEOUT (240s)"
                break

    return timing


def fmt(v, unit="ms"):
    if v is None:
        return "—"
    return f"{v:,.0f}{unit}"


def print_timing(t):
    print(f"\n{'─'*60}")
    print(f"  Run: {t['label']}")
    print(f"{'─'*60}")
    print(f"  WS connection established:  {fmt(t['conn_ms'])}")
    print(f"  → thinking (sync Lambda):   {fmt(t['t_thinking_ms'])}")
    print(f"  → first token (TTFT):       {fmt(t['t_first_token_ms'])}")
    print(f"    (async Lambda + AgentCore invoke + Bedrock R1 TTFT)")
    print(f"  → first tool chip:          {fmt(t['t_first_tool_start_ms'])}")
    if t["tool_rounds"]:
        print(f"\n  Tool round breakdown:")
        for i, tr in enumerate(t["tool_rounds"]):
            print(f"    [{i+1}] {tr['tool']:<22} "
                  f"server={fmt(tr['server_ms'])}  "
                  f"client={fmt(tr['client_ms'])}  "
                  f"wire≈{fmt(tr['wire_ms'])}")
    if t["bedrock_r1_ms"]:
        print(f"\n  Bedrock R1 (T0→first token):  {fmt(t['bedrock_r1_ms'])}")
    if t["final_bedrock_ms"] is not None:
        print(f"  Bedrock final round:           {fmt(t['final_bedrock_ms'])}")
    print(f"\n  → HITL awaiting_confirmation:  {fmt(t['t_hitl_ms'])}")
    print(f"  → DONE / terminal:             {fmt(t['t_done_ms'])}")
    print(f"  Terminal signal:               {t['terminal']}")
    print(f"\n  Signal sequence:")
    for elapsed, stype, brief in t["signal_log"]:
        print(f"    {elapsed:8.1f}ms  {stype:<26} {brief}")


def print_comparison(runs):
    print(f"\n{'═'*60}")
    print("  SUMMARY COMPARISON")
    print(f"{'═'*60}")
    headers = ["Metric", *[r["label"] for r in runs]]
    rows = [
        ("WS connect",         [r["conn_ms"]                  for r in runs]),
        ("→ thinking",         [r["t_thinking_ms"]            for r in runs]),
        ("→ first token",      [r["t_first_token_ms"]         for r in runs]),
        ("→ first tool chip",  [r["t_first_tool_start_ms"]    for r in runs]),
        ("→ HITL",             [r["t_hitl_ms"]                for r in runs]),
        ("→ DONE",             [r["t_done_ms"]                for r in runs]),
        ("Bedrock R1 TTFT",    [r["bedrock_r1_ms"]            for r in runs]),
        ("Final Bedrock round", [r["final_bedrock_ms"]        for r in runs]),
    ]
    col_w = 28
    print(f"  {'Metric':<{col_w}}", end="")
    for r in runs:
        print(f"  {r['label']:>12}", end="")
    print()
    print(f"  {'-'*col_w}", end="")
    for _ in runs:
        print(f"  {'─'*12}", end="")
    print()
    for label, vals in rows:
        print(f"  {label:<{col_w}}", end="")
        for v in vals:
            print(f"  {fmt(v):>12}", end="")
        print()

    # Tool breakdown per run
    print(f"\n  Tool latencies (server-side, ms):")
    for r in runs:
        tools = r.get("tool_rounds", [])
        line = "  " + r["label"] + ":  " + "  ".join(
            f"{tr['tool']}={tr['server_ms']}" for tr in tools
        ) if tools else "  " + r["label"] + ":  (no tools recorded)"
        print(line)


async def main_async(args):
    print("[auth] authenticating with Cognito …")
    t_auth0 = time.perf_counter()
    token = get_jwt(args.pool_id, args.client_id, args.username, args.password)
    auth_ms = (time.perf_counter() - t_auth0) * 1000
    print(f"[auth] got ID token  ({auth_ms:.0f}ms)\n")

    runs = []
    for i in range(args.runs):
        label = "cold" if i == 0 else f"warm-{i}"
        print(f"[run {i+1}/{args.runs}]  label={label}  {'(potential cold start)' if i == 0 else '(should be warm)'}")
        t = await run_timed_turn(args.wss_url, token, label, verbose=args.verbose)
        print_timing(t)
        runs.append(t)
        if i < args.runs - 1:
            gap = args.gap
            print(f"\n  [pause {gap}s before next run …]")
            await asyncio.sleep(gap)

    if len(runs) > 1:
        print_comparison(runs)


def main():
    p = argparse.ArgumentParser(description="MentorForge live latency probe")
    p.add_argument("--wss-url",   default=WSS_URL)
    p.add_argument("--pool-id",   default=POOL_ID)
    p.add_argument("--client-id", default=CLIENT_ID)
    p.add_argument("--username",  default=USERNAME)
    p.add_argument("--password",  default=PASSWORD)
    p.add_argument("--runs",      type=int, default=2,  help="number of consecutive turns (default 2)")
    p.add_argument("--gap",       type=int, default=5,  help="seconds between runs (default 5)")
    p.add_argument("--verbose",   action="store_true",  help="print each signal as it arrives")
    args = p.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
