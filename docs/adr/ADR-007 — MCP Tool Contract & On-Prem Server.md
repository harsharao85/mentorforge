---
tags: [adr, mentorforge, architecture]
created: 2026-06-01
adr-number: ADR-007
status: accepted
supersedes: []
superseded-by: []
depends-on: [ADR-002, ADR-003, ADR-006]
---

# (C) ADR-007 — MCP Tool Contract & On-Prem Server Framework

> **Date:** 2026-06-01 | **Status:** Accepted (ratifies the as-built `on-prem/mcp_server/`)
> **Depends on:** ADR-002 (AgentCore Gateway is the caller), ADR-003 (GraphRAG/Neo4j is the backend), ADR-006 (wire)

---

## Context

AgentCore Gateway must call the on-prem GraphRAG service to retrieve and reason over the graph. This is the **only** interface that crosses the wire — so the contract is the data-residency boundary: query strings in, redacted retrievals out, **no raw graph internals exposed to the agent**.

This ADR ratifies the contract **as built** in `on-prem/mcp_server/server.py`, and documents the gaps between it and the EX-story requirements.

---

## Options Considered (framework)

| Option | Verdict |
|---|---|
| **FastMCP (MCP Python SDK, `mcp.server.fastmcp`)** | **CHOSEN** — native MCP, `@mcp.tool()` decorators, streamable-HTTP ASGI app; clean tool schemas, no hand-rolled protocol |
| Plain FastAPI + custom REST | Rejected — would re-implement MCP framing by hand; AgentCore Gateway speaks MCP |
| Neo4j native MCP server | Rejected — **exposes raw Cypher**, pushing DB internals into the agent prompt (security + prompt-bloat) |

---

## Decision — the as-built contract (v1)

**Server:** FastMCP, exposed as a streamable-HTTP ASGI app (`mcp.streamable_http_app()`) under uvicorn.
**Auth:** Bearer-token middleware (`MCP_BEARER_TOKEN`); `/health` open. This is the signed bearer token from ADR-006 / AgentCore Identity.

**Three tools:**

| Tool | Signature | Returns | Purpose |
|---|---|---|---|
| `graph_retrieve` | `(query: str, top_k=5)` | `{answer_id, query, results(chunks), entity_context, community_context}` | Embed query (Ollama) → vector-search Neo4j chunks + entities → enrich with community context. Persists `answer_id` for later explanation. |
| `graph_traverse` | `(entity: str, depth=2)` (1–3) | traversal result | Walk entity relationships N hops — the who-to-meet / neighbourhood path. |
| `explain_path` | `(answer_id: str)` | `{nodes, communities}` that fed a prior retrieval | **Provenance** of a prior `graph_retrieve` — what grounded the answer. |

**Invariants:** MCP only (no raw Cypher to the agent); bearer-auth on every call; `answer_id` links a retrieval to its provenance for explainability/citations.

---

## Known gaps → contract v1.1 (flagged — they affect the EX stories)

Ratifying as-built surfaced **three gaps** between the tools and what the 3 EX stories need. These are not blockers for *wiring* (TASK-005) but they cap *story fidelity* and must be closed for the demo to fully land:

1. **No filters on `graph_retrieve`.** Stories need role / practice / engagement / stage-scoped retrieval (Story 1 = role+practice+engagement+stage). Today it's pure top-k vector search.
2. **No consent gating on `graph_retrieve` / `graph_traverse`.** This is the important one — **Story 2's "opted-out colleague (Jordan Chen) is hidden" cannot work**, and it undercuts the CHRO trust story (consent-aware recommendations). Consent (`discoverable` / `networking_opt_in`) must be filtered **at the tool layer**, not assumed upstream.
3. **`explain_path` semantics ≠ schema intent.** Built = "provenance of a prior answer." Graph Schema v2 / the stories also want **"why should I meet X"** = the reasoning *path between two entities*. The provenance tool is genuinely useful (citations), but the path-between-entities "why" narrative currently has to come from `graph_traverse`. Either rename/clarify, or add a `path_between(a, b)` mode in v1.1.

**Decision:** ratify v1 as the working contract; schedule **contract v1.1** (filters + consent gating + path-explain) as follow-up work. TASK-006 will hit gap #2 during Story-2 validation — that's the forcing function.

---

## Consequences

**Easier:** AgentCore Gateway has a stable, MCP-native, bearer-authed target; `answer_id`→provenance gives explainable RAG; no DB internals leak to the agent.
**Harder / risks:** the v1.1 gaps (esp. consent) gate full story fidelity; correlation-IDs for cross-boundary tracing (ADR-013) not yet wired.
**Closes off:** raw-Cypher / Neo4j-native MCP (security).

---

## What Would Revisit This Decision

- v1.1 lands (filters + consent + path-explain) → supersede this contract table with v1.1.
- AgentCore Gateway requires a tool-schema shape FastMCP can't express → revisit framing.
- Consent filtering proves too slow at the tool layer → push to a materialized consent view.

---

*Part of the MentorForge architecture decision log. ADRs are append-only — supersede, don't edit.*
