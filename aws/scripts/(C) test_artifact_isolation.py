"""
TASK-012 isolation test — no Bedrock, no agent turns.

Validates two properties of the /artifact-url endpoint:
  (a) Owner can fetch their own artifact key → HTTP 200 + presigned URL + readable S3 body
  (b) User2's token cannot access user1's key → HTTP 403

Run:
  python3 aws/scripts/'(C) test_artifact_isolation.py'

Env / hard-coded defaults:
  HISTORY_API_URL   — defaults to the deployed Lambda Function URL
  USER1_TOKEN       — Cognito ID token for the artifact owner (demo user)
  USER2_TOKEN       — Cognito ID token for a second user (no artifacts of their own)
  ARTIFACT_KEY      — a real key owned by user1 (auto-selected from /artifacts if not set)
"""

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

# ── configuration ─────────────────────────────────────────────────────────────

HISTORY_API = os.environ.get("HISTORY_API_URL", "")
if not HISTORY_API:
    sys.exit("Error: set HISTORY_API_URL to the HistoryApiUrl from cdk deploy outputs")

USER1_TOKEN = os.environ.get("USER1_TOKEN", "")
USER2_TOKEN = os.environ.get("USER2_TOKEN", "")
ARTIFACT_KEY = os.environ.get("ARTIFACT_KEY", "")


# ── helpers ───────────────────────────────────────────────────────────────────

def _get(url: str, token: str) -> tuple[int, dict | str]:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode()
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body


def _fetch_url(url: str) -> tuple[int, str]:
    """Plain GET — no auth header (presigned URL is self-authenticating)."""
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def _sub_from_token(token: str) -> str:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))
    return claims.get("sub", "?")


def _ok(label: str, detail: str = "") -> None:
    suffix = f"  →  {detail}" if detail else ""
    print(f"  ✓  {label}{suffix}")


def _fail(label: str, detail: str = "") -> None:
    suffix = f"  →  {detail}" if detail else ""
    print(f"  ✗  {label}{suffix}")
    sys.exit(1)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not USER1_TOKEN or not USER2_TOKEN:
        print("ERROR: USER1_TOKEN and USER2_TOKEN must be set.")
        sys.exit(1)

    user1_sub = _sub_from_token(USER1_TOKEN)
    user2_sub = _sub_from_token(USER2_TOKEN)
    print(f"User1 sub: {user1_sub}")
    print(f"User2 sub: {user2_sub}")
    print()

    # ── resolve artifact key for user1 ────────────────────────────────────────
    artifact_key = ARTIFACT_KEY
    if not artifact_key:
        # Pick the first artifact from the most recent thread.
        status, data = _get(f"{HISTORY_API}artifacts", USER1_TOKEN)
        if status != 200:
            print(f"ERROR: Could not list artifacts (HTTP {status}): {data}")
            sys.exit(1)
        arts = data.get("artifacts", []) if isinstance(data, dict) else []
        arts_with_key = [a for a in arts if a.get("s3Key")]
        if not arts_with_key:
            print("ERROR: No S3-backed artifacts found for user1 — run a chat turn first.")
            sys.exit(1)
        artifact_key = arts_with_key[0]["s3Key"]
        print(f"Auto-selected artifact key: {artifact_key}")
    else:
        print(f"Using supplied artifact key: {artifact_key}")
    print()

    assert artifact_key.startswith(f"learners/{user1_sub}/"), (
        f"Key {artifact_key!r} does not start with user1's prefix — test setup error"
    )

    # ── (a) Owner fetches their own artifact ──────────────────────────────────
    print("── Test (a): user1 fetches their own artifact ──────────────────────")
    url = f"{HISTORY_API}artifact-url?key={urllib.parse.quote(artifact_key, safe='')}"

    url = f"{HISTORY_API}artifact-url?key={urllib.parse.quote(artifact_key, safe='')}"

    status, body = _get(url, USER1_TOKEN)
    if status != 200:
        _fail(f"Expected 200, got {status}", str(body))
    presigned = body.get("url", "") if isinstance(body, dict) else ""
    if not presigned:
        _fail("Response has no 'url' field", str(body))
    _ok(f"HTTP {status} — presigned URL received")

    # Fetch the actual S3 body via the presigned URL
    s3_status, s3_body = _fetch_url(presigned)
    if s3_status != 200:
        _fail(f"S3 fetch returned HTTP {s3_status}", s3_body[:200])
    if not s3_body.strip():
        _fail("S3 body is empty")
    _ok(f"S3 body fetched ({len(s3_body)} chars, preview: {s3_body[:80]!r})")
    print()

    # ── (b) User2 cannot access user1's artifact ──────────────────────────────
    print("── Test (b): user2 attempts to access user1's artifact ─────────────")
    status2, body2 = _get(url, USER2_TOKEN)
    if status2 != 403:
        _fail(f"Expected 403, got {status2} — cross-learner isolation BROKEN", str(body2))
    error_msg = body2.get("error", "") if isinstance(body2, dict) else str(body2)
    _ok(f"HTTP 403 — Forbidden ({error_msg})")
    print()

    # ── (c) User1 cannot access a user2-prefix key (synthesized) ─────────────
    print("── Test (c): user1 gets 403 for a key in user2's prefix ────────────")
    fake_key = f"learners/{user2_sub}/fake-thread/fake-artifact"
    url_c = f"{HISTORY_API}artifact-url?key={urllib.parse.quote(fake_key, safe='')}"
    status_c, body_c = _get(url_c, USER1_TOKEN)
    if status_c != 403:
        _fail(f"Expected 403, got {status_c}", str(body_c))
    error_c = body_c.get("error", "") if isinstance(body_c, dict) else str(body_c)
    _ok(f"HTTP 403 — Forbidden ({error_c})")
    print()

    print("━" * 60)
    print("PASSED  all 3 isolation checks")
    print("  (a) Owner 200 + S3 body  ✓")
    print("  (b) Cross-user 403       ✓")
    print("  (c) Reverse cross 403    ✓")
    print("━" * 60)


if __name__ == "__main__":
    main()
