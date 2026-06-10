---
tags: [adr, architecture, mentorforge]
created: 2026-06-08
adr-number: ADR-029
status: accepted
task: TASK-012
refines: [ADR-023]
depends-on: [ADR-023, ADR-003b]
supersedes: []
superseded-by: []
---

# (C) ADR-029 — Artifact Storage: S3 Body, DynamoDB Index

> **Date:** 2026-06-08 | **Status:** Accepted | **Refines:** ADR-023 (episodic memory — artifact storage)
> **Renumber note:** originally drafted as "ADR-026" during TASK-012, but **026 was already taken** (Production Deployment Architecture). Renumbered to ADR-029 by Claudian to resolve the collision. This is the detailed record of the artifact-storage change that [[01 Architecture/(C) ADR-023 — Episodic Memory Model]]'s 2026-06-08 refinement note introduced.

## Context

TASK-010 wired artifact persistence through DynamoDB: each `graph_retrieve` / `graph_traverse` result is written as an `ARTIFACT#` item in `MentorForgeLearnerMemory` with the **full body** stored in the `content` attribute.

Two problems emerged as the demo stabilised:

1. **DynamoDB item size ceiling.** A `graph_retrieve` result can be a full onboarding document (hero docs are 2–8 KB of markdown). DynamoDB max item size is 400 KB. One graph call alone could return a chunk close to that limit if the RAG pipeline ever returns rich context. Storing full content in DDB is a latent size bomb.

2. **Right-pane depth.** TASK-011 moved depth *into* the right panel (chat is now ≤150 words). The right panel was showing a `line-clamp-3` preview of the full body already stored in DDB — but the entire document was being shipped over the wire from the Lambda to the SPA on every `listArtifacts` call, even for artifacts the user never opens.

## Decision

**Store artifact bodies in S3; demote DynamoDB `ARTIFACT#` items to lightweight index records.**

| Layer | What it stores | TTL |
|---|---|---|
| DynamoDB `ARTIFACT#` | `s3_key`, `title`, `preview` (first 200 chars), `source`, `ts` | none — durable |
| S3 `mentorforge-artifacts-<acct>-<region>` | Full body at `learners/<sub>/<thread>/<artifactId>` | bucket lifecycle optional |

The SPA fetches artifact index items cheaply on every thread load. When the user clicks a card to expand it, the SPA calls the History Lambda `/artifact-url?key=<s3_key>` → Lambda validates ownership (`key.startswith("learners/<sub>/")`) → generates a 5-minute presigned GET URL → browser fetches body directly from S3.

## Key design choices

**Per-learner key prefix as the isolation boundary.** The `learners/<sub>/` prefix is the only authorisation primitive needed: the Lambda checks it at presign-time. No GSI, no separate permissions table.

**SSE-S3 only (not KMS).** Consistent with TASK-003b (ADR-019 demo encryption policy). KMS CMK adds latency + cost; not warranted for demo.

**Backward compatibility — no backfill.** Old `ARTIFACT#` items (pre-TASK-012) carry `content` instead of `s3_key`. Both the history API and the SPA handle both shapes:
- History Lambda `_artifact_shape`: if `s3_key` present → return `s3Key + preview`; else → return `content`.
- SPA `ArtifactPanel`: if `s3Key` present → expandable (lazy S3 fetch); else → render `content` as static preview.

**CORS on S3.** Browser fetches the presigned URL directly. S3 bucket CORS allows GET from `https://demo.meringue-app.com` and `https://d29x1n3d931z8o.cloudfront.net`.

**Lambda fallback.** If `ARTIFACT_BUCKET_NAME` is unset (local dev / unit test), `append_artifact` falls back to writing full content to DDB — old behaviour, no code path breaks.

## Consequences

**Positive:**
- DDB item size no longer constrains artifact body length.
- `listArtifacts` is cheap: only index fields (no body bytes) over the wire.
- Right-panel depth is real: full document body loads on-demand, not preview-only.
- Ownership isolation is enforced at the key-prefix level — single line of code.

**Negative / risks:**
- Two-hop latency on first card expand: `/artifact-url` (presign) + S3 GET. Typical: ~200ms + ~80ms = ~280ms. Acceptable for demo.
- Presigned URL TTL of 5 minutes means an artifact opened after 5 min requires a fresh click (presign expires). For demo sessions this is fine.
- `autoDeleteObjects: true` on the CDK bucket adds a custom-resource Lambda — minor CDK complexity, acceptable for demo teardown hygiene.
- **Prod residency (P-17):** bodies are now corpus-derived content **at-rest in cloud S3** — beyond ADR-001's "transient retrievals cross." A production decision (Production Phase Backlog P-17), not a demo blocker.

## Alternatives considered

**Keep full body in DDB.** Rejected: item-size risk + wire cost growth with corpus depth.

**Stream body through the History Lambda.** Rejected: Lambda memory + execution-time cost for large docs; presigned URL is zero-cost per byte.

**Store only preview in DDB, no S3.** Rejected: violates the TASK-011/012 design principle — "right-panel documents actually carry the depth." Preview-only is insufficient.

---

*Refines ADR-023. ADRs are append-only — numbers are unique; this one resolves a same-day 026 collision.*
