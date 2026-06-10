"""
pytest configuration for Lambda unit tests.

Sets required env vars and stubs boto3 globally so no real AWS credentials
are needed. conftest.py is loaded by pytest before any test file, so the
stubs are in place when test modules import Lambda source files.
"""
import os
import sys
from unittest.mock import MagicMock

# ── env vars required by Lambda modules at import time ─────────────────────
os.environ.setdefault("MEMORY_TABLE_NAME",    "test-table")
os.environ.setdefault("USER_POOL_ID",         "us-east-1_TESTPOOL")
os.environ.setdefault("APP_CLIENT_ID",        "test-client-id")
os.environ.setdefault("ARTIFACT_BUCKET_NAME", "test-artifact-bucket")
os.environ.setdefault("COGNITO_REGION",       "us-east-1")
os.environ.setdefault("CONNECTIONS_TABLE",    "test-connections")
os.environ.setdefault("WS_CALLBACK_URL",      "https://test.execute-api.us-east-1.amazonaws.com/demo")
os.environ.setdefault("GENERATOR_IMPL",       "mock")

# ── stub boto3 so no real AWS calls can happen ─────────────────────────────
# Any module that does `import boto3` will receive this mock.
# Individual tests can override specific method return values on the mock
# if they need to assert DynamoDB/S3 interactions.
sys.modules["boto3"] = MagicMock()
sys.modules["botocore"] = MagicMock()
sys.modules["botocore.exceptions"] = MagicMock()

# ── add Lambda source directories to sys.path ──────────────────────────────
_lambdas = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(_lambdas, "ws", "send_message"))
sys.path.insert(0, os.path.join(_lambdas, "history"))
