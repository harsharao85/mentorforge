"""AgentCore Runtime entrypoint — Onboarding Concierge (TASK-005).

Serves the AgentCore Runtime contract:
  GET  /ping         → readiness probe; instant + import-light (TASK-005a invariant).
  POST /invocations  → ONE agent turn, STREAMED as NDJSON events.

The real loop: Bedrock ConverseStream (ADR-009 Claude Sonnet) + tool calls dispatched
to AgentCore Gateway over MCP (ADR-002/007, SigV4 per ADR-024). Text is streamed as it
generates; tool calls and the HITL meeting gate are emitted as structured events. The
Lambda-side AgentCoreGenerator maps each NDJSON event → an ADR-021 wire signal.

Heavy init (Bedrock client, Gateway/wire dial) is LAZY — first use inside /invocations,
never at import or in /ping. Within-session context only (ADR-023 parked — no durable store).

TASK-011 changes:
- Read tools within a round are executed in parallel (ThreadPoolExecutor).
  schedule_meeting remains the serial HITL gate — unchanged.
- Timing instrumentation: _timing events log Bedrock init and TTFT breakdown to
  the Lambda-side generator (CloudWatch), NOT relayed to the UI.
"""
import asyncio
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import uvicorn

import agent_def
import gateway_client

app = FastAPI()
logger = logging.getLogger(__name__)

REGION          = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID        = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-3-5-sonnet-20241022-v2:0")
TOKEN_BUDGET    = int(os.environ.get("TOKEN_BUDGET", "800"))
MAX_TOOL_ROUNDS = int(os.environ.get("MAX_TOOL_ROUNDS", "5"))
MAX_THROTTLE_RETRIES = 4

_bedrock = None  # lazy


def _bedrock_client():
    global _bedrock
    if _bedrock is None:
        import boto3
        _bedrock = boto3.client("bedrock-runtime", region_name=REGION)
    return _bedrock


def _ev(**kw) -> str:
    """Serialize one NDJSON event line."""
    return json.dumps(kw, ensure_ascii=False) + "\n"


@app.get("/ping")
def ping():
    return {"status": "healthy"}


# ── Bedrock ConverseStream with throttle retry/backoff ──────────────────────────

def _converse_stream(messages, system, tool_config):
    """Call converse_stream, retrying on ThrottlingException with exponential backoff.
    Returns the streaming response, or raises after exhausting retries."""
    from botocore.exceptions import ClientError
    delay = 0.5
    for attempt in range(MAX_THROTTLE_RETRIES + 1):
        try:
            return _bedrock_client().converse_stream(
                modelId=MODEL_ID,
                messages=messages,
                system=system,
                toolConfig=tool_config,
                inferenceConfig={"maxTokens": TOKEN_BUDGET, "temperature": 0.4},
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("ThrottlingException", "TooManyRequestsException") and attempt < MAX_THROTTLE_RETRIES:
                time.sleep(delay)
                delay *= 2
                continue
            raise


def _call_gateway_tool(tool: str, args: dict, learner_id: str) -> dict:
    """Dispatch a READ tool to the Gateway (async client) from sync code."""
    return asyncio.run(gateway_client.call_tool(tool, args, learner_id))


def _run_tools_parallel(read_tool_uses: list, learner_id: str) -> list:
    """Execute all READ tools concurrently, return (tu, result, latency_ms) in original order.

    Each tool fires an independent asyncio.run() in its own thread — safe because
    each creates a separate event loop. gateway_client._tool_name_map is a module-level
    cache; the benign race on cold-populate (two threads both call list_tools once) is
    acceptable — both writes are identical.
    """
    def run_one(tu):
        t0 = time.time()
        result = _call_gateway_tool(tu["name"], tu["input"], learner_id)
        return result, int((time.time() - t0) * 1000)

    n = max(1, len(read_tool_uses))
    with ThreadPoolExecutor(max_workers=n) as pool:
        futures = [pool.submit(run_one, tu) for tu in read_tool_uses]
        # Preserve submission order; total wait = max(individual latencies)
        return [(tu, *f.result()) for tu, f in zip(read_tool_uses, futures)]


def _summarize(tool: str, result: dict, limit: int = 200) -> str:
    """Clean, human-readable tool_end summary for the UI chips (matches the mock's
    convention that tool_end.result is a concise summary string, not a raw blob)."""
    try:
        if tool == "graph_retrieve":
            n = len(result.get("results", []))
            ents = len(result.get("entity_context", []))
            top = (result.get("results") or [{}])[0].get("doc_title")
            parts = [f"{n} docs"]
            if top:
                parts.append(f"top: {top}")
            if ents:
                parts.append(f"{ents} entities")
            return " · ".join(parts)
        if tool == "graph_traverse":
            people = result.get("people", [])
            if people:
                return " · ".join(f"{p['relationship'].replace('_', ' ')}: {p['name']}" for p in people)
            return f"{len(result.get('nodes', []))} related entities"
        if tool == "explain_path":
            if result.get("narrative"):
                return result["narrative"]
            docs = result.get("documents_sourced", [])
            return f"provenance: {len(docs)} docs" if docs else "no path found"
    except Exception:  # noqa: BLE001 — summary must never break the turn
        pass
    s = json.dumps(result, ensure_ascii=False, default=str)
    return s if len(s) <= limit else s[:limit] + "…"


# ── The turn ────────────────────────────────────────────────────────────────────

def _run_turn(payload: dict):
    """Yield NDJSON event lines for one turn. All failure modes terminate with an
    `error` event — never a silent hang."""
    action     = payload.get("action", "start_turn")
    learner_id = payload.get("learner_id", "")

    # Deterministic error-path test hook (mirrors the mock's "__error__" trigger).
    if payload.get("message", "").strip() == "__error__":
        yield _ev(type="error", message="Simulated failure — error channel confirmed.")
        return

    try:
        if action == "confirm":
            yield from _resume_confirmed(payload)
        elif action == "cancel":
            yield from _resume_cancelled(payload)
        else:
            yield from _start_turn(payload, learner_id)
    except Exception as exc:  # noqa: BLE001 — last-resort: client MUST get a terminal signal
        yield _ev(type="error", message=f"The assistant hit an error completing this turn. ({type(exc).__name__})")


def _start_turn(payload: dict, learner_id: str):
    text = payload.get("message", "")
    system   = [{"text": agent_def.SYSTEM_PROMPT}]
    tools    = {"tools": agent_def.TOOL_SPECS}
    messages = [{"role": "user", "content": [{"text": text}]}]

    yield _ev(type="thinking")

    for _round in range(MAX_TOOL_ROUNDS):
        # ── Bedrock init timing ─────────────────────────────────────────────────
        t_before_converse = time.time()
        resp = _converse_stream(messages, system, tools)
        t_after_converse = time.time()
        # _timing events are internal telemetry — logged by the generator, NOT relayed to UI.
        yield _ev(type="_timing", phase="bedrock_init_ms",
                  value=int((t_after_converse - t_before_converse) * 1000),
                  round=_round)

        assistant_content = []   # reconstruct the assistant turn for history
        cur_text = []
        cur_tool = None          # {"toolUseId","name","_input_parts":[...]}
        tool_uses = []           # completed tool-use blocks this round
        stop_reason = "end_turn"
        first_token_t = None     # wall time of first token — for TTFT instrumentation

        for event in resp["stream"]:
            if "contentBlockStart" in event:
                start = event["contentBlockStart"]["start"]
                if "toolUse" in start:
                    cur_tool = {"toolUseId": start["toolUse"]["toolUseId"],
                                "name": start["toolUse"]["name"], "_input_parts": []}
            elif "contentBlockDelta" in event:
                delta = event["contentBlockDelta"]["delta"]
                if "text" in delta:
                    if first_token_t is None:
                        first_token_t = time.time()
                        yield _ev(type="_timing", phase="bedrock_ttft_ms",
                                  value=int((first_token_t - t_after_converse) * 1000),
                                  round=_round)
                    cur_text.append(delta["text"])
                    yield _ev(type="token", text=delta["text"])      # ← real streaming
                elif "toolUse" in delta and cur_tool is not None:
                    cur_tool["_input_parts"].append(delta["toolUse"].get("input", ""))
            elif "contentBlockStop" in event:
                if cur_tool is not None:
                    raw = "".join(cur_tool["_input_parts"]) or "{}"
                    try:
                        cur_tool["input"] = json.loads(raw)
                    except json.JSONDecodeError:
                        cur_tool["input"] = {}
                    tool_uses.append(cur_tool)
                    assistant_content.append({"toolUse": {
                        "toolUseId": cur_tool["toolUseId"], "name": cur_tool["name"],
                        "input": cur_tool["input"]}})
                    cur_tool = None
                elif cur_text:
                    assistant_content.append({"text": "".join(cur_text)})
                    cur_text = []
            elif "messageStop" in event:
                stop_reason = event["messageStop"].get("stopReason", "end_turn")

        if stop_reason != "tool_use" or not tool_uses:
            yield _ev(type="done")
            return

        # ── Tool dispatch ──────────────────────────────────────────────────────
        messages.append({"role": "assistant", "content": assistant_content})
        tool_results = []

        # ACTION tool check: schedule_meeting is the HITL gate — first action tool in
        # the round wins; pause immediately, do not execute read tools in the same round.
        for tu in tool_uses:
            if tu["name"] in agent_def.ACTION_TOOL_NAMES:
                args  = tu["input"]
                who   = args.get("with", "your colleague")
                mtype = args.get("type", "1:1")
                dur   = args.get("duration_min", 30)
                yield _ev(type="awaiting_confirmation",
                          prompt=f"Book a {dur}-min {mtype} with {who}?",
                          action={"tool": tu["name"], "args": args})
                return  # turn pauses here; confirm/cancel resumes via the Lambda

        # Pure READ round — fire all tools in parallel (TASK-011).
        # Emit all tool_start chips first (instant); client sees them all at once.
        read_tool_uses = [tu for tu in tool_uses if tu["name"] in agent_def.GRAPH_TOOL_NAMES]
        for tu in read_tool_uses:
            yield _ev(type="tool_start", tool=tu["name"], args=tu["input"])

        try:
            executed = _run_tools_parallel(read_tool_uses, learner_id)
        except Exception as exc:  # noqa: BLE001 — surface tool/wire failure
            raise RuntimeError(f"parallel tool execution failed: {exc}") from exc

        for tu, result, latency_ms in executed:
            yield _ev(type="tool_end", tool=tu["name"],
                      result=_summarize(tu["name"], result), latency_ms=latency_ms)
            tool_results.append({"toolResult": {
                "toolUseId": tu["toolUseId"],
                "content": [{"json": result}]}})

        messages.append({"role": "user", "content": tool_results})

    # Tool-round budget exhausted without a final answer.
    yield _ev(type="done")


def _resume_confirmed(payload: dict):
    """Execute the stubbed booking for the confirmed pending action (V1 stub)."""
    pending = payload.get("pending_action", {}) or {}
    tool = pending.get("tool", "schedule_meeting")
    args = pending.get("args", {})
    who  = args.get("with", "your colleague")

    yield _ev(type="tool_start", tool=tool, args=args)
    time.sleep(0.05)
    yield _ev(type="tool_end", tool=tool, result="booked", latency_ms=50)
    yield _ev(type="action_done", tool=tool, result=f"Calendar invite sent to {who}.")
    yield _ev(type="token", text=f" Done — the invite to {who} is in your calendar.")
    yield _ev(type="done")


def _resume_cancelled(payload: dict):
    yield _ev(type="token", text="No problem — skipped for now. You can book it any time from your task list.")
    yield _ev(type="done")


@app.post("/invocations")
async def invocations(request: Request):
    payload = await request.json()
    # Sync generator is iterated in Starlette's threadpool, so asyncio.run() inside
    # the Gateway calls is safe (no running loop on that worker thread).
    return StreamingResponse(_run_turn(payload), media_type="application/x-ndjson")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
