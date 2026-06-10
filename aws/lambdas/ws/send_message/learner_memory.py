"""
LearnerMemory — thin DynamoDB writer for persistent chat history (ADR-023 demo slice).

Table:  MentorForgeLearnerMemory
pk:     LEARNER#<cognito-sub>
sk patterns:
  THREAD#<threadId>            — thread metadata
  MSG#<threadId>#<isoTs>       — one message (user or assistant)
  ARTIFACT#<isoTs>#<uuid4>     — one surfaced document / people result

TASK-012: artifact bodies stored in S3 (ADR-029).
  ARTIFACT# items are now index entries: s3_key + title + preview (first 200 chars).
  Full body at s3_key = learners/<learner_id>/<thread_id>/<artifact_id>.
  Backward compat: old items (pre-TASK-012) carry a `content` field instead —
  the history API and SPA handle both shapes.

All writes are best-effort: a failure is logged and swallowed so it never
interrupts the agent turn that the learner is waiting on.
"""
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3

log = logging.getLogger(__name__)

TABLE            = os.environ.get("MEMORY_TABLE_NAME", "MentorForgeLearnerMemory")
ARTIFACT_BUCKET  = os.environ.get("ARTIFACT_BUCKET_NAME", "")
_db   = boto3.resource("dynamodb")
_tbl  = _db.Table(TABLE)
_s3   = boto3.client("s3")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_thread(learner_id: str, thread_id: str, title: str) -> None:
    """Create the THREAD# item if it doesn't exist; always touch last_active_at."""
    try:
        pk  = f"LEARNER#{learner_id}"
        sk  = f"THREAD#{thread_id}"
        now = _now()
        _tbl.update_item(
            Key={"pk": pk, "sk": sk},
            UpdateExpression=(
                "SET title = if_not_exists(title, :t), "
                "created_at = if_not_exists(created_at, :n), "
                "last_active_at = :n, "
                "thread_id = :id, "
                "msg_count = if_not_exists(msg_count, :z)"
            ),
            ExpressionAttributeValues={
                ":t":  title[:80] if title else "Untitled",
                ":n":  now,
                ":id": thread_id,
                ":z":  0,
            },
        )
    except Exception:
        log.exception("ensure_thread failed — skipping")


def _bump_thread(learner_id: str, thread_id: str) -> None:
    try:
        _tbl.update_item(
            Key={"pk": f"LEARNER#{learner_id}", "sk": f"THREAD#{thread_id}"},
            UpdateExpression="SET last_active_at = :n ADD msg_count :one",
            ExpressionAttributeValues={":n": _now(), ":one": 1},
        )
    except Exception:
        log.exception("_bump_thread failed — skipping")


def append_message(
    learner_id: str,
    thread_id: str,
    role: str,
    text: str,
    tool_calls: list | None = None,
) -> None:
    """Write one MSG# item and bump the thread's activity counter."""
    if not text and not tool_calls:
        return
    try:
        now = _now()
        pk  = f"LEARNER#{learner_id}"
        sk  = f"MSG#{thread_id}#{now}"
        _tbl.put_item(Item={
            "pk":         pk,
            "sk":         sk,
            "thread_id":  thread_id,
            "role":       role,
            "text":       text or "",
            "tool_calls": tool_calls or [],
            "ts":         now,
        })
        _bump_thread(learner_id, thread_id)
    except Exception:
        log.exception("append_message failed — skipping")


def append_artifact(
    learner_id: str,
    thread_id: str,
    source: str,
    title: str,
    content: str,
) -> None:
    """Write artifact body to S3 and store a lightweight index item in DynamoDB.

    S3 key: learners/<learner_id>/<thread_id>/<artifact_id>
    DynamoDB ARTIFACT# item: s3_key + title + preview (first 200 chars).

    If ARTIFACT_BUCKET_NAME is not set (e.g. local dev), falls back to writing
    full content to DynamoDB (old behaviour) so the turn still works.
    """
    try:
        now         = _now()
        artifact_id = str(uuid.uuid4())
        pk          = f"LEARNER#{learner_id}"
        sk          = f"ARTIFACT#{now}#{artifact_id}"

        if ARTIFACT_BUCKET and content:
            s3_key = f"learners/{learner_id}/{thread_id}/{artifact_id}"
            _s3.put_object(
                Bucket=ARTIFACT_BUCKET,
                Key=s3_key,
                Body=content.encode("utf-8"),
                ContentType="text/plain; charset=utf-8",
            )
            _tbl.put_item(Item={
                "pk":          pk,
                "sk":          sk,
                "artifact_id": artifact_id,
                "thread_id":   thread_id,
                "source":      source,
                "title":       title,
                "s3_key":      s3_key,
                "preview":     content[:200],
                "ts":          now,
            })
        else:
            # Fallback: no bucket configured — store full content in DDB (dev/test).
            _tbl.put_item(Item={
                "pk":          pk,
                "sk":          sk,
                "artifact_id": artifact_id,
                "thread_id":   thread_id,
                "source":      source,
                "title":       title,
                "content":     content,
                "ts":          now,
            })
    except Exception:
        log.exception("append_artifact failed — skipping")
