---
tags: [adr, mentorforge, architecture]
created: 2026-06-08
adr-number: ADR-025
status: accepted
supersedes: []
superseded-by: []
refines: [ADR-007]
depends-on: [ADR-007]
---

# (C) ADR-025 — MCP Tool Contract v1.1 (filters · path-explain · traversal name resolution)

> **Date:** 2026-06-08 | **Status:** Accepted | **Refines:** ADR-007 (realizes its flagged "contract v1.1" gaps)
> **Trigger:** TASK-005 proved Story 1 end-to-end, but the **people/why differentiator** — the thing that makes MentorForge more than a chatbot over docs — has fidelity gaps. This ADR specifies the contract changes; TASK-007 builds them.

---

## Context

ADR-007 ratified the as-built v1 MCP contract (`graph_retrieve` / `graph_traverse` / `explain_path`) and **explicitly flagged three v1.1 gaps**. TASK-005's live run confirmed they cap story fidelity:

1. **No filters on `graph_retrieve`** — retrieval is pure top-k; can't scope to a learner's role / practice / engagement / journey stage.
2. **`graph_traverse` doesn't cleanly resolve onboarding people** — manager / buddy / practice-lead / engagement-lead names don't come back as first-class, named results, so the "schedule a 1:1 with *X*" beat can't name *X*.
3. **`explain_path` is provenance, not "why"** — it returns what grounded a prior answer (good for citations), but the stories need **the relationship path between two entities** = the "why should I meet this person" narrative.

**Consent filtering is NOT in this v1.1.** Consent is deferred to production (decided) and conveyed verbally in the demo — see ADR-007 gap #2 and [[01 Architecture/(C) ADR-026 — Production Deployment Architecture]].

---

## Decision — contract v1.1

| Tool | v1 (ADR-007) | v1.1 change |
|---|---|---|
| `graph_retrieve(query, top_k)` | pure top-k vector search | **add optional filters**: `role`, `practice`, `engagement`, `stage`. Metadata-scoped retrieval; absent filters = v1 behavior (backward compatible). |
| `graph_traverse(entity, depth)` | raw neighbourhood walk | **typed onboarding traversal** that resolves named people for the onboarding edges — `manager`, `buddy`, `practice_lead`, `engagement_lead` — returning `{name, role, relationship, why}` per person, not raw nodes. |
| `explain_path(answer_id)` | provenance of a prior answer | **add a second mode `path_between(a, b)`** returning the relationship path between two entities (the "why meet X" narrative). Keep the provenance mode for citations — the two are distinct and both useful. |

**Invariants unchanged from ADR-007:** MCP-only (no raw Cypher to the agent), bearer-auth every call, `answer_id` links retrieval → provenance.

---

## Consequences

- **Easier:** all three EX stories land through the tools — content *scoped* to the learner, people *named*, "why" *explained*. The differentiator becomes demonstrable, not just claimed.
- **Backward compatible:** filters are optional; provenance mode preserved. Existing wiring (TASK-005) keeps working.
- **Still open (deferred, not regressed):** consent gating at the tool layer → production (ADR-026). Multi-hop reasoning beyond the named onboarding edges → future.

## What Would Revisit This

- Consent lands → add consent filtering to `graph_retrieve` / `graph_traverse` (production).
- A customer's on-prem RAG can't express typed traversal → fall back to `path_between` over a generic graph.
- Filter cardinality grows → push to a materialized per-learner view.

---

*Refines ADR-007. ADRs are append-only — this extends the contract, it does not edit ADR-007 in place.*
