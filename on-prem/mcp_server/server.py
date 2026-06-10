import os
import uuid

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

import neo4j_client
import ollama_client

_BEARER_TOKEN = os.environ["MCP_BEARER_TOKEN"]

# The MCP SDK enforces DNS-rebinding protection by validating the Host header against
# an allow-list (defaults to localhost). AgentCore Gateway reaches us over the Cloudflare
# wire (ADR-006), so the Host header is the tunnel domain — which the default rejects with
# 421 "Invalid Host header". The bearer token (above) is the real authentication boundary,
# so we relax host/origin validation for the wire. Prod hardens this with mTLS + a stable
# hostname allow-list (ADR-006).
_TRANSPORT_SECURITY = TransportSecuritySettings(
    enable_dns_rebinding_protection=False,
    allowed_hosts=["*"],
    allowed_origins=["*"],
)


class _BearerAuth(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return JSONResponse({"status": "ok"})
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != _BEARER_TOKEN:
            return Response("Unauthorized", status_code=401)
        return await call_next(request)


mcp = FastMCP("MentorForge On-Prem MCP Server", transport_security=_TRANSPORT_SECURITY)


@mcp.tool()
async def graph_retrieve(
    query: str,
    top_k: int = 5,
    role: str | None = None,
    practice: str | None = None,
    engagement: str | None = None,
    stage: str | None = None,
) -> dict:
    """Embed the query, vector-search Neo4j chunks + entities, enrich with graph context.

    ADR-025 v1.1: optional role/practice/engagement/stage scope the retrieval. Absent =
    pure top-k (backward compatible). Scoping is applied at the query layer — the filters
    are folded into the embedded query to bias retrieval toward the learner's context.
    """
    scope = {"role": role, "practice": practice, "engagement": engagement, "stage": stage}
    active = {k: v for k, v in scope.items() if v}
    embed_query = query
    if active:
        ctx = " ".join(f"{k}={v}" for k, v in active.items())
        embed_query = f"{query} | context: {ctx}"

    embedding = await ollama_client.embed(embed_query)
    driver = await neo4j_client.get_driver()

    async with driver.session() as session:
        chunks = await neo4j_client.search_chunks(session, embedding, top_k)
        entities, communities = await neo4j_client.search_entities(session, embedding, top_k)

    answer_id = str(uuid.uuid4())
    if chunks or communities:
        async with driver.session() as session:
            await neo4j_client.persist_answer(
                session,
                answer_id=answer_id,
                query=query,
                chunk_ids=[c["chunk_id"] for c in chunks],
                community_ids=[c["community_id"] for c in communities],
            )

    return {
        "answer_id": answer_id,
        "query": query,
        "filters_applied": active,
        "results": chunks,
        "entity_context": entities,
        "community_context": communities,
    }


@mcp.tool()
async def graph_traverse(entity: str, depth: int = 2) -> dict:
    """Find the named onboarding people for a new hire (ADR-025 typed traversal).

    For a Person, resolves manager / buddy / practice_lead / engagement_lead as named
    people with {name, role, relationship, why}. For a non-person entity (or no match),
    falls back to the raw relationship neighbourhood (v1 behaviour).
    """
    if not 1 <= depth <= 3:
        raise ValueError("depth must be between 1 and 3")
    driver = await neo4j_client.get_driver()
    async with driver.session() as session:
        people = await neo4j_client.resolve_onboarding_people(session, entity)
        if people:
            return {"root_entity": entity, "people": people}
        # Fallback: not a Person (or no onboarding edges) — raw neighbourhood.
        return await neo4j_client.traverse_entity(session, entity, depth)


@mcp.tool()
async def explain_path(answer_id: str = "", a: str = "", b: str = "") -> dict:
    """Two modes (ADR-025):
    - provenance: explain_path(answer_id=...) → nodes/communities that grounded a prior retrieval (citations).
    - path_between: explain_path(a=..., b=...) → relationship path between two entities (the 'why meet X' narrative).
    """
    driver = await neo4j_client.get_driver()
    async with driver.session() as session:
        if a and b:
            return await neo4j_client.path_between(session, a, b)
        if answer_id:
            return await neo4j_client.explain_answer(session, answer_id)
        raise ValueError("explain_path requires either answer_id (provenance) or both a and b (path_between)")


# Expose as ASGI app for uvicorn; middleware is added before first request.
app = mcp.streamable_http_app()
app.add_middleware(_BearerAuth)
