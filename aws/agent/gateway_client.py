"""Gateway client — the agent's hop to AgentCore Gateway over MCP, SigV4-signed.

Per ADR-024: Runtime→Gateway is a machine-to-machine hop authenticated with the
Runtime execution role via SigV4 (service 'bedrock-agentcore'), NOT a learner JWT.
The Gateway proxies to the on-prem MCP server with the outbound bearer (ADR-006/007),
so the bearer never lives in this container.

Lazy by contract (TASK-005a invariant): nothing here runs at import or during /ping.
The Gateway URL is read from SSM on first use; the MCP session is opened per tool call.

The READ tools (graph_retrieve / graph_traverse / explain_path) are dispatched here.
Tool names may be Gateway-prefixed (e.g. 'graphtools___graph_retrieve'); we discover the
live names once via list_tools and match by suffix so the agent can use logical names.
"""
import json
import os

import boto3
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

REGION = os.environ.get("AWS_REGION", "us-east-1")
GATEWAY_URL_PARAM = os.environ.get("GATEWAY_URL_PARAM", "/mentorforge/demo/gateway/url")
SERVICE = "bedrock-agentcore"

_gateway_url = None        # cached after first SSM read
_tool_name_map = None      # logical name -> live Gateway tool name


class _SigV4HttpxAuth(httpx.Auth):
    """Signs each outgoing httpx request with SigV4 for the Gateway (machine identity)."""
    requires_request_body = True

    def __init__(self):
        self._creds = boto3.Session().get_credentials()

    def auth_flow(self, request):
        body = request.content or b""
        aws_req = AWSRequest(method=request.method, url=str(request.url),
                             data=body, headers=dict(request.headers))
        # Frozen creds each call so rotation (the execution role) is picked up.
        SigV4Auth(self._creds.get_frozen_credentials(), SERVICE, REGION).add_auth(aws_req)
        request.headers.update(dict(aws_req.headers))
        yield request


def _httpx_client_factory(headers=None, timeout=None, auth=None):
    # mcp streamable-http calls this to build its client; we inject SigV4 auth.
    return httpx.AsyncClient(headers=headers, timeout=timeout, auth=_SigV4HttpxAuth())


def _resolve_gateway_url() -> str:
    global _gateway_url
    if _gateway_url is None:
        # Allow a direct override (handy for local/iteration); else read SSM.
        _gateway_url = os.environ.get("GATEWAY_URL") or (
            boto3.client("ssm", region_name=REGION)
            .get_parameter(Name=GATEWAY_URL_PARAM)["Parameter"]["Value"]
        )
    return _gateway_url


def _logical(name: str) -> str:
    # Gateway prefixes target tools as '<target>___<tool>'. Match by suffix.
    return name.split("___")[-1]


async def call_tool(tool: str, args: dict, learner_id: str = "") -> dict:
    """Open an MCP session to the Gateway, call `tool`, return its parsed result dict.

    learner_id is carried as a payload claim for per-call audit (ADR-024) without a JWT.
    """
    global _tool_name_map
    url = _resolve_gateway_url()
    payload = dict(args)
    if learner_id:
        payload["_learner_id"] = learner_id  # audit claim, ignored by read tools

    async with streamablehttp_client(url, httpx_client_factory=_httpx_client_factory) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            if _tool_name_map is None:
                listed = await session.list_tools()
                _tool_name_map = {_logical(t.name): t.name for t in listed.tools}
            live_name = _tool_name_map.get(tool, tool)
            result = await session.call_tool(live_name, payload)

    if result.content and getattr(result.content[0], "text", None):
        try:
            return json.loads(result.content[0].text)
        except json.JSONDecodeError:
            return {"text": result.content[0].text}
    return {}
