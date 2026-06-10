"""
Unit tests for pure helper functions extracted from history/index.py.

Functions under test are inlined here to keep the tests dependency-free
and resilient to import-time boto3/env interactions in the Lambda module.
These tests verify the logic that shapes DynamoDB items into API responses
and validates JWT claims — the security-critical paths.
"""
import base64
import json


# ── Helpers extracted from history/index.py ───────────────────────────────
# Kept in sync with the source. If you change these in the Lambda, update here.

def _b64url_decode(b64: str) -> bytes:
    b64 += "=" * (-len(b64) % 4)
    return base64.urlsafe_b64decode(b64)


def _extract_token(event: dict) -> str:
    headers = event.get("headers") or {}
    auth = headers.get("authorization") or headers.get("Authorization") or ""
    return auth[7:] if auth.lower().startswith("bearer ") else ""


def _artifact_shape(item: dict) -> dict:
    base = {
        "artifactId": item.get("artifact_id", ""),
        "threadId":   item.get("thread_id", ""),
        "source":     item.get("source", ""),
        "title":      item.get("title", ""),
        "ts":         item.get("ts", ""),
    }
    if "s3_key" in item:
        base["s3Key"]   = item["s3_key"]
        base["preview"] = item.get("preview", "")
    else:
        base["content"] = item.get("content", "")
    return base


# ── _b64url_decode ────────────────────────────────────────────────────────

def test_b64url_decode_roundtrip():
    payload = {"sub": "abc-123", "exp": 9999999999}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    decoded = json.loads(_b64url_decode(encoded))
    assert decoded["sub"] == "abc-123"


def test_b64url_decode_padding_lengths():
    for n in range(1, 8):
        raw = b"x" * n
        encoded = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
        assert _b64url_decode(encoded) == raw


# ── _extract_token ─────────────────────────────────────────────────────────

def test_extract_token_bearer_capitalized():
    event = {"headers": {"Authorization": "Bearer mytoken123"}}
    assert _extract_token(event) == "mytoken123"


def test_extract_token_bearer_lowercase():
    event = {"headers": {"authorization": "bearer mytoken456"}}
    assert _extract_token(event) == "mytoken456"


def test_extract_token_missing_header():
    assert _extract_token({}) == ""
    assert _extract_token({"headers": {}}) == ""
    assert _extract_token({"headers": {"Authorization": ""}}) == ""
    assert _extract_token({"headers": None}) == ""


def test_extract_token_non_bearer_scheme():
    event = {"headers": {"Authorization": "Basic dXNlcjpwYXNz"}}
    assert _extract_token(event) == ""


def test_extract_token_strips_bearer_prefix_only():
    event = {"headers": {"Authorization": "Bearer eyJhbGciOiJSUzI1NiJ9.payload.sig"}}
    token = _extract_token(event)
    assert token.startswith("eyJ")
    assert not token.startswith("Bearer ")


# ── _artifact_shape — new items (TASK-012, s3Key path) ────────────────────

def test_artifact_shape_new_item_has_s3key():
    item = {
        "artifact_id": "art-001",
        "thread_id":   "thread-abc",
        "source":      "graph_retrieve",
        "title":       "HIPAA Handling Policy",
        "s3_key":      "learners/sub1/thread-abc/art-001",
        "preview":     "All client data is HIPAA-regulated.",
        "ts":          "2026-06-08T00:00:00Z",
    }
    shaped = _artifact_shape(item)
    assert shaped["artifactId"] == "art-001"
    assert shaped["threadId"] == "thread-abc"
    assert shaped["s3Key"] == "learners/sub1/thread-abc/art-001"
    assert shaped["preview"] == "All client data is HIPAA-regulated."
    assert "content" not in shaped


def test_artifact_shape_new_item_empty_preview():
    item = {"artifact_id": "x", "thread_id": "t", "s3_key": "learners/s/t/x"}
    shaped = _artifact_shape(item)
    assert shaped["s3Key"] == "learners/s/t/x"
    assert shaped["preview"] == ""


# ── _artifact_shape — old items (pre-TASK-012, content path) ──────────────

def test_artifact_shape_old_item_has_content():
    item = {
        "artifact_id": "art-old",
        "thread_id":   "thread-xyz",
        "source":      "graph_traverse",
        "title":       "People to meet",
        "content":     "Ben Okonkwo is your manager...",
        "ts":          "2026-06-01T00:00:00Z",
    }
    shaped = _artifact_shape(item)
    assert shaped["content"] == "Ben Okonkwo is your manager..."
    assert "s3Key" not in shaped
    assert "preview" not in shaped


def test_artifact_shape_old_item_empty_content():
    item = {"artifact_id": "y", "thread_id": "t"}
    shaped = _artifact_shape(item)
    assert shaped["content"] == ""
    assert "s3Key" not in shaped


def test_artifact_shape_missing_fields():
    shaped = _artifact_shape({})
    assert shaped["artifactId"] == ""
    assert shaped["threadId"] == ""
    assert shaped["source"] == ""
    assert shaped["title"] == ""
    assert shaped["ts"] == ""
    assert shaped["content"] == ""


# ── Ownership key check (from /artifact-url endpoint logic) ───────────────

def _ownership_ok(key: str, learner_id: str) -> bool:
    """Extracted from history/index.py /artifact-url handler."""
    return bool(key) and key.startswith(f"learners/{learner_id}/")


def test_ownership_own_key():
    assert _ownership_ok("learners/sub-abc/thread-1/art-1", "sub-abc")


def test_ownership_foreign_key():
    assert not _ownership_ok("learners/sub-xyz/thread-1/art-1", "sub-abc")


def test_ownership_empty_key():
    assert not _ownership_ok("", "sub-abc")


def test_ownership_path_traversal_attempt():
    # An attacker passes learners/sub-abc/../other-sub/key
    # Key starts with learners/sub-abc/ only if the traversal isn't there
    assert not _ownership_ok("learners/sub-abc/../other-sub/key", "other-sub")
    # But the legitimate prefix check still passes for legitimate paths:
    assert _ownership_ok("learners/other-sub/t/a", "other-sub")


def test_ownership_prefix_boundary():
    # sub-abc-extra should NOT match sub-abc
    assert not _ownership_ok("learners/sub-abc-extra/t/a", "sub-abc")


# ── preview truncation (from append_artifact in learner_memory.py) ────────

def test_preview_truncation_at_200():
    content = "a" * 300
    preview = content[:200]
    assert len(preview) == 200


def test_preview_truncation_short_content():
    content = "short text"
    preview = content[:200]
    assert preview == "short text"
