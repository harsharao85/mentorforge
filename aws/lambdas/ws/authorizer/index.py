"""
$connect Lambda REQUEST authorizer.
Validates the Cognito JWT passed as ?token=<jwt> on the WS handshake URL.

AUTHENTICATION ONLY — no RBAC. ADR-010 governs authorisation when it lands.

Demo-grade validation: checks issuer, audience, and expiry using the standard
library only (no external pip deps, no Docker bundling required).
# TODO (ADR-010 / prod): add RSA signature verification against the Cognito
#   JWKS endpoint using python-jose[cryptography].
"""
import base64
import json
import os
import time

REGION        = os.environ["AWS_REGION"]
USER_POOL_ID  = os.environ["USER_POOL_ID"]
APP_CLIENT_ID = os.environ["APP_CLIENT_ID"]
EXPECTED_ISS  = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"


def _b64url_decode(b64: str) -> bytes:
    b64 += "=" * (-len(b64) % 4)
    return base64.urlsafe_b64decode(b64)


def _decode_claims(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Malformed JWT")
    return json.loads(_b64url_decode(parts[1]))


def handler(event, context):
    token      = (event.get("queryStringParameters") or {}).get("token", "")
    method_arn = event["methodArn"]
    try:
        learner_id = _validate(token)
        return _policy("Allow", method_arn, learner_id)
    except Exception as exc:
        print(f"[authorizer] rejected: {exc}")
        return _policy("Deny", method_arn, "")


def _validate(token: str) -> str:
    if not token:
        raise ValueError("Missing token")

    claims = _decode_claims(token)

    if claims.get("exp", 0) < time.time():
        raise ValueError("Token expired")

    if claims.get("iss") != EXPECTED_ISS:
        raise ValueError(f"Unexpected issuer: {claims.get('iss')}")

    # ID tokens use 'aud'; access tokens use 'client_id'
    aud = claims.get("aud") or claims.get("client_id")
    if aud != APP_CLIENT_ID:
        raise ValueError(f"Unexpected audience: {aud}")

    sub = claims.get("sub", "")
    if not sub:
        raise ValueError("No sub claim")

    return sub  # learnerId = Cognito sub


def _policy(effect: str, method_arn: str, learner_id: str) -> dict:
    return {
        "principalId": learner_id or "anonymous",
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [{
                "Action":   "execute-api:Invoke",
                "Effect":   effect,
                "Resource": method_arn,
            }],
        },
        "context": {"learnerId": learner_id},
    }
