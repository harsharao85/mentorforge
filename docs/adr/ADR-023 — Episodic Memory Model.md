---
tags: [adr, mentorforge, architecture, memory]
created: 2026-06-08
adr-number: ADR-023
status: accepted
supersedes: []
superseded-by: []
depends-on: [ADR-021, ADR-009]
sources: ["[[01 Architecture/(C) Memory Architecture Evaluation]]"]
---

# (C) ADR-023 — Episodic Memory Model

> **Date:** 2026-06-08 | **Status:** Accepted (**un-parked** — was deferred during the demo build)
> **Design basis:** [[01 Architecture/(C) Memory Architecture Evaluation]] (already done).

---

## Context

Memory was deliberately parked during the demo build — the spine ran **within-session only**. Driving the live SPA exposed the gap directly: every login opens fresh, nothing persists, there's no conversation history. For an assistant whose pitch is "it knows your org and your journey," forgetting the user between logins is a credibility hole. **Product owner decision (2026-06-08): persistence comes into the demo.** This un-parks ADR-023.

## Decision

**Build memory ourselves in DynamoDB** (per the memory eval — *not* AgentCore Memory; that re-introduces control-plane coupling and opaque summarization, wrong for an OSS/transparency project; re-evaluate in a later phase).

**Two tables, split by lifecycle** (the eval's design):
- `MentorForgeConnections` — **unchanged**: ephemeral routing, `connectionId` PK, 4h TTL, deleted on `$disconnect`.
- **`MentorForgeLearnerMemory` (new)** — durable, **no TTL**, keyed by **`learnerId` (Cognito sub)**. Single-table; `pk = LEARNER#<id>`, `sk` discriminates record type.

**Demo slice (what we build now)** — exactly what the three-pane UI needs:
| `sk` prefix | Holds | Powers |
|---|---|---|
| `THREAD#<id>` | a conversation thread (title, created, last-active) | left pane (history list) |
| `MSG#<thread>#<seq>` | a message in a thread (role, content, signals) | replaying a past conversation |
| `ARTIFACT#<id>` | a generated/surfaced document (title, body/ref, source thread) | right pane (saved documents) |

One `Query(pk=LEARNER#<id>)` loads a learner's threads + artifacts on login. Messages load per-thread on open.

> **Refinement (2026-06-08) — artifact bodies → S3, pulled into the demo.** Product-owner call: store artifact **bodies in S3 object storage** (SSE-S3), with the `ARTIFACT#` DynamoDB record demoted to an **index** (`s3_key` + title + preview + metadata); the SPA fetches bodies via **presigned URLs**. Right tier per job, lifts the DynamoDB 400KB cap, and is a talkable storage pattern. Built in [[Interface/tasks/TASK-012-artifact-storage-s3]]; recorded in detail as [[01 Architecture/(C) ADR-029 — Artifact Storage — S3 Body, DynamoDB Index]]. Threads/messages stay in DynamoDB. (Prod: the *at-rest residency* of persisted retrieval results remains a production decision — Production Phase Backlog P-17.)

**Deferred (NOT this slice):** journey-state projection, semantic facts, the nudge engine, cross-session summarization/compaction — the fuller episodic model stays future. This slice is conversational + artifact persistence only.

## Scope line — demo-grade now, prod-grade governance later

- **In now (demo-grade):** functional persistence — threads, messages, artifacts, per learner, survive login.
- **Stays production (P-05 / ADR-026 R4):** PII classification, CMK encryption, retention + right-to-be-forgotten, residency messaging. The demo persists Priya's data in DynamoDB (default encryption); the governance layer is a production concern, not this slice.

## Consequences

- **Easier:** a real assistant that remembers you across logins — materially stronger demo; one new table.
- **Wiring:** thread/message persistence hooks into the turn lifecycle; `learnerId` (already on the connection record from `$connect`) is the partition key. The `ResponseGenerator` seam is untouched — persistence is a layer around it, not inside it.
- **Closes off nothing** — the deferred records (`JOURNEY`/`FACT#`/nudges) are additive `sk` types on the same table later.

## What Would Revisit This

- Prod governance lands → layer P-05 controls onto this table (don't re-architect).
- Memory volume/summarization needs grow → add compaction (`SUMMARY` records) per the eval.
- Multi-tenant → tenant scoping on the partition key.

---

*Design basis: the memory eval. ADRs are append-only.*
