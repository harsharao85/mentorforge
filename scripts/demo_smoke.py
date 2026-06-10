#!/usr/bin/env python3
"""Demo smoke test (TASK-008) — runs the OPENING TURN of all 3 EX stories end-to-end
through the live AgentCore Runtime and asserts coherent signals. Fails loud (exit 1)
if any story errors, calls no tools, or doesn't reach a terminal/HITL state.

Uses the `aws` CLI (no boto3 dependency). Invoked by demo_up.sh after the wire is up.
"""
import base64
import json
import os
import subprocess
import sys
import tempfile

RUNTIME_ARN = os.environ.get("MENTORFORGE_RUNTIME_ARN", "")
QUALIFIER   = os.environ.get("MENTORFORGE_RUNTIME_QUALIFIER", "mentorforge_demo_endpoint")

STORIES = [
    ("Story 1 — Soft Landing",
     "Hi, I'm Priya Nair, a new Senior Consultant on the Data practice, Atlas-Health "
     "engagement. It's my first day — what should I focus on and who should I meet?"),
    ("Story 2 — Who's Done This Before",
     "I need to set up Unity Catalog governance for Atlas-Health and I've never done it "
     "here. Who has done this before, and what should I read?"),
    ("Story 3 — 30-Day Nudge",
     "I'm coming up on my 30-day mark. What should I do for my 30-day check-in, and is "
     "there a community I should join?"),
]


def run_turn(message: str, turn_id: str) -> list[dict]:
    payload = base64.b64encode(json.dumps({
        "action": "start_turn", "message": message, "turn_id": turn_id, "learner_id": "",
    }).encode()).decode()
    with tempfile.NamedTemporaryFile(mode="r", suffix=".ndjson") as out:
        proc = subprocess.run(
            ["aws", "bedrock-agentcore", "invoke-agent-runtime",
             "--agent-runtime-arn", RUNTIME_ARN, "--qualifier", QUALIFIER,
             "--payload", payload, "--content-type", "application/json", out.name],
            capture_output=True, text=True, timeout=180,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"InvokeAgentRuntime failed: {proc.stderr.strip()[:200]}")
        events = []
        for line in open(out.name):
            line = line.strip()
            if line:
                try: events.append(json.loads(line))
                except json.JSONDecodeError: pass
        return events


def check(name: str, events: list[dict]) -> tuple[bool, str]:
    # The Runtime emits FLAT NDJSON events ({"type":"tool_end","tool":…,"result":…}).
    # (The {type,turnId,seq,data} wrapping is added later by the Lambda-side generator.)
    types = [e.get("type") for e in events]
    if "error" in types:
        msg = next((e.get("message") for e in events if e.get("type") == "error"), "?")
        return False, f"error signal: {msg}"
    tool_ends = [e for e in events if e.get("type") == "tool_end"]
    if not tool_ends:
        return False, "no tool calls (agent didn't reason over the graph)"
    if "done" not in types and "awaiting_confirmation" not in types:
        return False, f"no terminal state (got: {types[-3:]})"
    tokens = sum(1 for t in types if t == "token")
    tools = ", ".join(f"{e.get('tool')}→{str(e.get('result', ''))[:40]}" for e in tool_ends)
    terminal = "awaiting_confirmation" if "awaiting_confirmation" in types else "done"
    return True, f"{len(tool_ends)} tool calls, {tokens} tokens, ended={terminal} | {tools}"


def main() -> int:
    if not RUNTIME_ARN:
        sys.exit("Error: set MENTORFORGE_RUNTIME_ARN to the AgentCore Runtime ARN (from CDK stack outputs)")
    print("=== MentorForge demo smoke — 3 EX story openers ===\n")
    ok_all = True
    for i, (name, msg) in enumerate(STORIES):
        print(f"▶ {name}")
        try:
            events = run_turn(msg, f"smoke-{i}-aaaaaaaaaaaaaaaaaaaaaaaaaaaa")
            ok, detail = check(name, events)
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"exception: {e}"
        print(f"  {'✅ PASS' if ok else '❌ FAIL'} — {detail}\n")
        ok_all = ok_all and ok
    print("=== SMOKE PASSED ===" if ok_all else "=== SMOKE FAILED ===")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
