"""
sendMessage Lambda — experience-layer transport (ADR-021).

Handles three inbound actions:
  sendMessage — start a new turn via ResponseGenerator
  confirm     — resume after learner confirmed a gated action
  cancel      — resume after learner cancelled a gated action

Enforces a per-user turn cap (the cost backstop — ADR-021).
HITL state persists in DynamoDB pending_action field.

Async fan-out: sendMessage sends thinking immediately, then self-invokes with
InvocationType=Event so the AgentCore call runs beyond the 29s API GW window.
TASK-010: persistence wraps the turn (learner_memory) — seam (response_generator.py) untouched.
"""
import decimal
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

from agentcore_generator import AgentCoreGenerator
from response_generator import MockSocraticGenerator
import learner_memory
import signals as s

TABLE           = os.environ["CONNECTIONS_TABLE"]
WS_CALLBACK_URL = os.environ["WS_CALLBACK_URL"]
TURN_LIMIT      = int(os.environ.get("TURN_LIMIT", "20"))
TURN_WINDOW_HRS = int(os.environ.get("TURN_WINDOW_HOURS", "1"))

_db        = boto3.resource("dynamodb")
_tbl       = _db.Table(TABLE)
# Composition root: select the generator impl.
_generator = (MockSocraticGenerator()
              if os.environ.get("GENERATOR_IMPL", "agentcore").lower() == "mock"
              else AgentCoreGenerator())
_lambda    = boto3.client("lambda")


def handler(event, context):
    # Keep-warm ping — EventBridge fires this every 5 min (TASK-011).
    # Short-circuit immediately so the function stays warm with zero side effects.
    if event.get("_keepwarm"):
        return {"statusCode": 200}

    # Async processor path — self-invoked beyond the 29s API GW integration window
    if event.get("_async"):
        mgmt = boto3.client("apigatewaymanagementapi", endpoint_url=WS_CALLBACK_URL)
        _run_async_turn(event, mgmt)
        return {"statusCode": 200}

    conn_id = event["requestContext"]["connectionId"]
    body    = json.loads(event.get("body") or "{}")
    action  = body.get("action", "sendMessage")

    mgmt = boto3.client(
        "apigatewaymanagementapi",
        endpoint_url=WS_CALLBACK_URL,
    )

    if action == "confirm":
        _handle_confirm(conn_id, mgmt)
    elif action == "cancel":
        _handle_cancel(conn_id, mgmt)
    else:
        text      = body.get("payload", {}).get("message", body.get("text", ""))
        thread_id = body.get("payload", {}).get("threadId") or str(uuid.uuid4())
        _handle_new_turn(conn_id, text, mgmt, thread_id)

    return {"statusCode": 200}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _post(mgmt, conn_id: str, payload: bytes) -> None:
    """Send a signal to the client; silently drop if connection is gone."""
    try:
        mgmt.post_to_connection(ConnectionId=conn_id, Data=payload)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("GoneException", "410"):
            return
        raise


def _strip_decimals(obj):
    """DynamoDB returns numbers as Decimal — convert to int/float for JSON serialization."""
    if isinstance(obj, list):
        return [_strip_decimals(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _strip_decimals(v) for k, v in obj.items()}
    if isinstance(obj, decimal.Decimal):
        return int(obj) if obj == int(obj) else float(obj)
    return obj


def _get_conn(conn_id: str) -> dict:
    resp = _tbl.get_item(Key={"connectionId": conn_id})
    return _strip_decimals(resp.get("Item", {}))


def _check_turn_cap(conn: dict, conn_id: str) -> bool:
    """Return True (under cap) or False (exceeded). Atomically increments on allow."""
    now          = datetime.now(timezone.utc)
    window_start = datetime.fromisoformat(conn.get("turn_window_start", now.isoformat()))
    turn_count   = int(conn.get("turn_count", 0))

    if now - window_start > timedelta(hours=TURN_WINDOW_HRS):
        turn_count   = 0
        window_start = now

    if turn_count >= TURN_LIMIT:
        return False

    _tbl.update_item(
        Key={"connectionId": conn_id},
        UpdateExpression="SET turn_count = :tc, turn_window_start = :ws",
        ExpressionAttributeValues={
            ":tc": turn_count + 1,
            ":ws": window_start.isoformat(),
        },
    )
    return True


# ── Artifact extraction ───────────────────────────────────────────────────────

def _maybe_save_artifact(learner_id: str, thread_id: str, tc: dict) -> None:
    """Persist a graph tool result as an artifact."""
    tool    = tc.get("tool", "")
    content = tc.get("result", "")
    if not content:
        return
    if tool == "graph_retrieve":
        # result format: "N docs · top: <Title>"
        title = content.split("top:")[-1].strip() if "top:" in content else "Retrieved documents"
        learner_memory.append_artifact(learner_id, thread_id, tool, title, content)
    elif tool == "graph_traverse":
        learner_memory.append_artifact(learner_id, thread_id, tool, "People to meet", content)
    elif tool == "explain_path":
        learner_memory.append_artifact(learner_id, thread_id, tool, "Relationship path", content)


# ── Turn handlers ─────────────────────────────────────────────────────────────

def _handle_new_turn(conn_id: str, text: str, mgmt, thread_id: str) -> None:
    conn       = _get_conn(conn_id)
    if not conn:
        return
    learner_id = conn.get("learnerId", "unknown")

    turn_id = str(uuid.uuid4())

    if not _check_turn_cap(conn, conn_id):
        _post(mgmt, conn_id, s.error("Turn limit reached. Please try again in an hour.", turn_id, 0))
        return

    # ── Persistence: ensure thread exists; record user message ──
    if learner_id != "unknown":
        learner_memory.ensure_thread(learner_id, thread_id, (text or "Untitled")[:60])
        learner_memory.append_message(learner_id, thread_id, role="user", text=text)

    # Clear any stale pending action
    _tbl.update_item(
        Key={"connectionId": conn_id},
        UpdateExpression="REMOVE pending_action",
    )

    # Immediate feedback — client sees this before the 29s API GW frame closes
    _post(mgmt, conn_id, s.thinking(turn_id, 0))

    # Fire the full AgentCore turn asynchronously — runs beyond the 29s window
    _lambda.invoke(
        FunctionName=os.environ["AWS_LAMBDA_FUNCTION_NAME"],
        InvocationType="Event",
        Payload=json.dumps({
            "_async":       True,
            "connectionId": conn_id,
            "text":         text,
            "turnId":       turn_id,
            "threadId":     thread_id,
            "learnerId":    learner_id,
        }).encode(),
    )


def _run_async_turn(event: dict, mgmt) -> None:
    conn_id    = event["connectionId"]
    text       = event["text"]
    turn_id    = event["turnId"]
    thread_id  = event.get("threadId", "")
    learner_id = event.get("learnerId", "unknown")

    gen = _generator.start_turn(text, turn_id)
    next(gen)  # discard thinking — already sent by the sync path

    persist = bool(thread_id and learner_id != "unknown")
    pending_action = None
    assistant_text = ""
    tool_calls     = []

    # ── Relay loop — relay behavior is unchanged; persistence is a side-effect ──
    for payload in gen:
        _post(mgmt, conn_id, payload)
        msg = json.loads(payload)
        t   = msg["type"]

        if t == "token" and persist:
            assistant_text += msg["data"].get("text", "")

        elif t == "tool_end" and persist:
            tc = {
                "tool":       msg["data"].get("tool", ""),
                "result":     msg["data"].get("result", ""),
                "latency_ms": msg["data"].get("latency_ms", 0),
            }
            tool_calls.append(tc)
            _maybe_save_artifact(learner_id, thread_id, tc)

        elif t == "awaiting_confirmation":
            pending_action = {
                "turn_id":    turn_id,
                "action":     msg["data"]["action"],
                "thread_id":  thread_id,
                "learner_id": learner_id,
            }
            if persist and assistant_text:
                learner_memory.append_message(
                    learner_id, thread_id, role="assistant",
                    text=assistant_text, tool_calls=tool_calls,
                )

        elif t == "done" and persist and assistant_text:
            learner_memory.append_message(
                learner_id, thread_id, role="assistant",
                text=assistant_text, tool_calls=tool_calls,
            )

    if pending_action:
        _tbl.update_item(
            Key={"connectionId": conn_id},
            UpdateExpression="SET pending_action = :pa",
            ExpressionAttributeValues={":pa": pending_action},
        )


def _handle_confirm(conn_id: str, mgmt) -> None:
    conn    = _get_conn(conn_id)
    pending = conn.get("pending_action")
    if not pending:
        return

    _tbl.update_item(
        Key={"connectionId": conn_id},
        UpdateExpression="REMOVE pending_action",
    )

    thread_id  = pending.get("thread_id", "")
    learner_id = pending.get("learner_id", "unknown")
    persist    = bool(thread_id and learner_id != "unknown")
    action_result = ""

    for payload in _generator.resume_confirmed(pending["action"], pending["turn_id"]):
        _post(mgmt, conn_id, payload)
        if persist:
            msg = json.loads(payload)
            if msg["type"] == "action_done":
                action_result = msg["data"].get("result", "")

    if persist and action_result:
        learner_memory.append_message(
            learner_id, thread_id, role="assistant", text=action_result,
        )


def _handle_cancel(conn_id: str, mgmt) -> None:
    conn    = _get_conn(conn_id)
    pending = conn.get("pending_action")
    if not pending:
        return

    _tbl.update_item(
        Key={"connectionId": conn_id},
        UpdateExpression="REMOVE pending_action",
    )

    for payload in _generator.resume_cancelled(pending["action"], pending["turn_id"]):
        _post(mgmt, conn_id, payload)
