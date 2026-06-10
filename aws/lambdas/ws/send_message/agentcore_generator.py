"""AgentCoreGenerator — the real ResponseGenerator (TASK-005).

Replaces MockSocraticGenerator. Invokes AgentCore Runtime (InvokeAgentRuntime),
**iterates the streamed NDJSON response** the Onboarding Concierge emits, and maps each
runtime event → an ADR-021 wire signal. Real streaming: text arrives as many `token`
signals as it generates — not one blob at the end.

Error hardening (spec item 6, QA's #1 UX risk): the whole turn is wrapped; the invoke is
retried with backoff on AgentCore throttling; ANY failure emits a terminal `error` signal.
A failed turn never leaves the client on a silent, indefinite spinner.

Seam discipline: this file is the generator impl. It does NOT touch the transport relay,
the signal protocol, or the ResponseGenerator ABC.

learner_id audit claim (ADR-024): the InvokeAgentRuntime payload carries a `learner_id`
field, but the ABC only hands this generator (text, turn_id) — so its value is "" in V1.
Populating the real learner_id needs a seam touch (see the FLAG note). The plumbing is
ready; only the value is deferred.

TASK-011 — timing instrumentation:
  _timing events emitted by the Runtime (type="_timing", phase, value, round) are logged
  here and NOT relayed to the UI. They attribute the thinking→first-token gap:
    invoke_agent_runtime_ms  — Lambda side: HTTP setup to first streaming byte
    bedrock_init_ms          — Runtime side: _converse_stream() call overhead per round
    bedrock_ttft_ms          — Runtime side: time from converse response to first token

  All three land in the Lambda's CloudWatch log group as structured JSON for Claudian.
"""
import json
import logging
import os
import time
from typing import Generator

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

import boto3  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402

import signals as s  # noqa: E402
from response_generator import ResponseGenerator  # noqa: E402

RUNTIME_ARN = os.environ.get("AGENT_RUNTIME_ARN", "")
QUALIFIER   = os.environ.get("AGENT_RUNTIME_QUALIFIER", "mentorforge_demo_endpoint")
REGION      = os.environ.get("AWS_REGION", "us-east-1")
MAX_THROTTLE_RETRIES = 4
_SAFE_ERROR = "Sorry — I hit a problem completing that. Please try again in a moment."


class AgentCoreGenerator(ResponseGenerator):
    def __init__(self):
        self._client = boto3.client("bedrock-agentcore", region_name=REGION)

    # ── streaming invoke ────────────────────────────────────────────────────────
    def _invoke_lines(self, payload: dict, turn_id: str):
        """Invoke the Runtime (retry/backoff on throttle) and yield NDJSON lines as
        they stream back. Raises on terminal failure; the caller maps that to `error`.

        TASK-011 timing: logs two metrics to CloudWatch:
          invoke_agent_runtime_ms  — time from send to first HTTP response byte (includes
                                     AgentCore control-plane overhead + Runtime startup).
          time_to_first_event_ms   — same as above measured to the first streamed NDJSON
                                     line (same as invoke_agent_runtime_ms in practice,
                                     since the Runtime streams from the first event).
        """
        delay = 0.5
        last_exc = None
        t_invoke_start = time.time()
        for attempt in range(MAX_THROTTLE_RETRIES + 1):
            try:
                resp = self._client.invoke_agent_runtime(
                    agentRuntimeArn=RUNTIME_ARN,
                    qualifier=QUALIFIER,
                    runtimeSessionId=turn_id,            # session continuity within the turn (start→confirm)
                    payload=json.dumps(payload).encode("utf-8"),
                )
                break
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                last_exc = exc
                if code in ("ThrottlingException", "TooManyRequestsException") and attempt < MAX_THROTTLE_RETRIES:
                    time.sleep(delay); delay *= 2; continue
                raise
        else:  # pragma: no cover
            raise last_exc

        t_response = time.time()
        logger.info(json.dumps({
            "metric": "invoke_agent_runtime_ms",
            "turn_id": turn_id,
            "value": int((t_response - t_invoke_start) * 1000),
        }))

        body = resp.get("response", resp.get("body"))
        first_event = True
        for raw in _iter_ndjson(body):
            if first_event:
                t_first = time.time()
                logger.info(json.dumps({
                    "metric": "time_to_first_event_ms",
                    "turn_id": turn_id,
                    "value": int((t_first - t_invoke_start) * 1000),
                }))
                first_event = False
            yield raw

    def _stream_turn(self, payload: dict, turn_id: str, seq: int, drop_first_thinking: bool):
        """Map streamed runtime events → ADR-021 signals. `drop_first_thinking` skips the
        runtime's `thinking` event because the transport already sent one on the sync path."""
        thinking_dropped = not drop_first_thinking
        for line in self._invoke_lines(payload, turn_id):
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            etype = ev.get("type")

            if etype == "_timing":
                # Internal telemetry from the Runtime — log to CloudWatch, never relay to UI.
                logger.info(json.dumps({
                    "metric": ev.get("phase", "unknown"),
                    "turn_id": turn_id,
                    "value": ev.get("value", 0),
                    "round": ev.get("round", 0),
                }))
                continue
            elif etype == "thinking":
                if not thinking_dropped:
                    thinking_dropped = True       # client already has one from the sync path
                    continue
                yield s.thinking(turn_id, seq); seq += 1
            elif etype == "token":
                yield s.token(ev.get("text", ""), turn_id, seq); seq += 1
            elif etype == "tool_start":
                yield s.tool_start(ev.get("tool", ""), ev.get("args", {}), turn_id, seq); seq += 1
            elif etype == "tool_end":
                yield s.tool_end(ev.get("tool", ""), str(ev.get("result", "")), int(ev.get("latency_ms", 0)), turn_id, seq); seq += 1
            elif etype == "awaiting_confirmation":
                yield s.awaiting_confirmation(
                    prompt=ev.get("prompt", "Confirm this action?"),
                    action=ev.get("action", {}),
                    turn_id=turn_id, seq=seq); seq += 1
            elif etype == "action_done":
                yield s.action_done(ev.get("tool", ""), str(ev.get("result", "")), turn_id, seq); seq += 1
            elif etype == "error":
                yield s.error(ev.get("message", _SAFE_ERROR), turn_id, seq); seq += 1
            elif etype == "done":
                yield s.done(turn_id, seq); seq += 1

    # ── ResponseGenerator contract ──────────────────────────────────────────────
    def start_turn(self, text: str, turn_id: str) -> Generator[bytes, None, None]:
        # First yield is discarded by the transport (it already sent `thinking`).
        yield s.thinking(turn_id, 0)
        try:
            payload = {"action": "start_turn", "message": text, "turn_id": turn_id, "learner_id": ""}
            yield from self._stream_turn(payload, turn_id, seq=1, drop_first_thinking=True)
        except Exception:  # noqa: BLE001 — terminal error, never a silent spinner
            yield s.error(_SAFE_ERROR, turn_id, 999)

    def resume_confirmed(self, pending_action: dict, turn_id: str) -> Generator[bytes, None, None]:
        try:
            payload = {"action": "confirm", "turn_id": turn_id, "pending_action": pending_action, "learner_id": ""}
            yield from self._stream_turn(payload, turn_id, seq=100, drop_first_thinking=False)
        except Exception:  # noqa: BLE001
            yield s.error(_SAFE_ERROR, turn_id, 999)

    def resume_cancelled(self, pending_action: dict, turn_id: str) -> Generator[bytes, None, None]:
        try:
            payload = {"action": "cancel", "turn_id": turn_id, "pending_action": pending_action, "learner_id": ""}
            yield from self._stream_turn(payload, turn_id, seq=100, drop_first_thinking=False)
        except Exception:  # noqa: BLE001
            yield s.error(_SAFE_ERROR, turn_id, 999)


# ── streaming body adapter ──────────────────────────────────────────────────────

def _iter_ndjson(body):
    """Yield text lines from the InvokeAgentRuntime response body, whatever shape it is:
    a botocore StreamingBody (.iter_lines), an EventStream (chunk events), or raw bytes/str.
    Incremental — does not buffer the whole turn (that's the point of streaming)."""
    if body is None:
        return
    # StreamingBody — the common case for an x-ndjson StreamingResponse.
    if hasattr(body, "iter_lines"):
        for raw in body.iter_lines():
            yield raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
        return
    # EventStream — accumulate chunk bytes, split on newlines.
    if hasattr(body, "__iter__") and not isinstance(body, (bytes, bytearray, str)):
        buf = ""
        for event in body:
            chunk = b""
            if isinstance(event, dict):
                chunk = (event.get("chunk", {}) or {}).get("bytes", b"")
            if chunk:
                buf += chunk.decode("utf-8")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    yield line
        if buf:
            yield buf
        return
    # Raw bytes / str.
    raw = body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else str(body)
    for line in raw.split("\n"):
        yield line
