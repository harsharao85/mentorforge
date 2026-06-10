"""
History read API — Lambda Function URL (AuthType=NONE).
JWT validated in-function (same issuer/audience/expiry pattern as WS authorizer).

Routes (HTTP method inferred from path; all GET except OPTIONS preflight):
  GET /threads                         → list learner's threads (newest first)
  GET /threads/{threadId}/messages     → messages for one thread (chronological)
  GET /artifacts?threadId=<id>         → artifacts for one thread (newest first)
  GET /artifact-url?key=<s3_key>       → short-TTL presigned GET URL for one artifact body

TASK-012: artifact bodies live in S3 (ADR-029). The /artifacts endpoint returns
lightweight index items (s3Key + preview). /artifact-url issues a 5-min presigned
URL after validating ownership: the key must start with learners/<sub>/ (the requesting
learner's own prefix). Old items (pre-TASK-012) carry a `content` field — returned
as-is for backward compat.
"""
import base64
import json
import os
import time

import boto3
from boto3.dynamodb.conditions import Key

TABLE            = os.environ["MEMORY_TABLE_NAME"]
POOL_ID          = os.environ["USER_POOL_ID"]
CLIENT           = os.environ["APP_CLIENT_ID"]
REGION           = os.environ.get("COGNITO_REGION", os.environ.get("AWS_REGION", "us-east-1"))
ISSUER           = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL_ID}"
ARTIFACT_BUCKET  = os.environ.get("ARTIFACT_BUCKET_NAME", "")
PRESIGN_TTL_SECS = 300   # 5 minutes — short enough to be single-session safe

_db  = boto3.resource("dynamodb")
_tbl = _db.Table(TABLE)
_s3  = boto3.client("s3", region_name=REGION)


def handler(event, context):
    method = (event.get("requestContext") or {}).get("http", {}).get("method", "GET").upper()

    if method == "OPTIONS":
        return _cors({})

    token = _extract_token(event)
    try:
        learner_id = _validate_jwt(token)
    except Exception as exc:
        return _error(401, str(exc))

    path = (event.get("requestContext") or {}).get("http", {}).get("path", "/").rstrip("/") or "/"
    qs   = event.get("queryStringParameters") or {}
    pk   = f"LEARNER#{learner_id}"

    # GET /threads
    if path in ("/threads", "/"):
        items   = _query_prefix(pk, "THREAD#")
        threads = sorted(
            [_thread_shape(i) for i in items],
            key=lambda t: t.get("last_active_at", ""),
            reverse=True,
        )
        return _ok({"threads": threads})

    # GET /threads/{threadId}/messages
    parts = path.strip("/").split("/")
    if len(parts) == 3 and parts[0] == "threads" and parts[2] == "messages":
        thread_id = parts[1]
        items = _query_prefix(pk, f"MSG#{thread_id}#")
        msgs  = sorted([_msg_shape(i) for i in items], key=lambda m: m.get("ts", ""))
        return _ok({"messages": msgs})

    # GET /artifacts?threadId=...
    if path == "/artifacts":
        items = _query_prefix(pk, "ARTIFACT#")
        arts  = [_artifact_shape(i) for i in items]
        tid   = qs.get("threadId")
        if tid:
            arts = [a for a in arts if a.get("threadId") == tid]
        arts.sort(key=lambda a: a.get("ts", ""), reverse=True)
        return _ok({"artifacts": arts})

    # GET /artifact-url?key=<s3_key>
    # Ownership check: key must start with learners/<sub>/ — prevents cross-learner access.
    if path == "/artifact-url":
        key = qs.get("key", "")
        expected_prefix = f"learners/{learner_id}/"
        if not key or not key.startswith(expected_prefix):
            return _error(403, "Forbidden — key does not belong to this learner")
        if not ARTIFACT_BUCKET:
            return _error(503, "Artifact bucket not configured")
        try:
            url = _s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": ARTIFACT_BUCKET, "Key": key},
                ExpiresIn=PRESIGN_TTL_SECS,
            )
        except Exception as exc:
            return _error(500, f"Presign failed: {exc}")
        return _ok({"url": url})

    return _error(404, "Not found")


# ── DynamoDB helpers ────────────────────────────────────────────────────────

def _query_prefix(pk: str, sk_prefix: str) -> list:
    resp = _tbl.query(
        KeyConditionExpression=Key("pk").eq(pk) & Key("sk").begins_with(sk_prefix)
    )
    return resp.get("Items", [])


# ── JWT helpers (no external deps — stdlib only) ────────────────────────────

def _extract_token(event) -> str:
    headers = event.get("headers") or {}
    auth = headers.get("authorization") or headers.get("Authorization") or ""
    return auth[7:] if auth.lower().startswith("bearer ") else ""


def _b64url_decode(b64: str) -> bytes:
    b64 += "=" * (-len(b64) % 4)
    return base64.urlsafe_b64decode(b64)


def _validate_jwt(token: str) -> str:
    if not token:
        raise ValueError("Missing token")
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Malformed JWT")
    claims = json.loads(_b64url_decode(parts[1]))
    if claims.get("exp", 0) < time.time():
        raise ValueError("Token expired")
    if claims.get("iss") != ISSUER:
        raise ValueError("Unexpected issuer")
    aud = claims.get("aud") or claims.get("client_id")
    if aud != CLIENT:
        raise ValueError("Unexpected audience")
    sub = claims.get("sub", "")
    if not sub:
        raise ValueError("No sub claim")
    return sub


# ── Response shaping ────────────────────────────────────────────────────────

def _thread_shape(item: dict) -> dict:
    return {
        "threadId":       item.get("thread_id", ""),
        "title":          item.get("title", "Untitled"),
        "created_at":     item.get("created_at", ""),
        "last_active_at": item.get("last_active_at", ""),
        "msg_count":      int(item.get("msg_count", 0)),
    }


def _msg_shape(item: dict) -> dict:
    return {
        "threadId":   item.get("thread_id", ""),
        "role":       item.get("role", ""),
        "text":       item.get("text", ""),
        "tool_calls": item.get("tool_calls", []),
        "ts":         item.get("ts", ""),
    }


def _artifact_shape(item: dict) -> dict:
    """Return artifact index item.

    New items (TASK-012): s3Key + preview (body fetched separately via /artifact-url).
    Old items (pre-TASK-012): content field — returned as-is for backward compat.
    """
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


# ── HTTP responses ──────────────────────────────────────────────────────────

_CORS_HEADERS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Headers": "authorization,content-type",
    "Access-Control-Allow-Methods": "GET,OPTIONS",
}


def _ok(body: dict) -> dict:
    return {
        "statusCode": 200,
        "headers":    {"Content-Type": "application/json", **_CORS_HEADERS},
        "body":       json.dumps(body),
    }


def _cors(body: dict) -> dict:
    return {
        "statusCode": 204,
        "headers":    _CORS_HEADERS,
        "body":       "",
    }


def _error(code: int, msg: str) -> dict:
    return {
        "statusCode": code,
        "headers":    {"Content-Type": "application/json", **_CORS_HEADERS},
        "body":       json.dumps({"error": msg}),
    }
