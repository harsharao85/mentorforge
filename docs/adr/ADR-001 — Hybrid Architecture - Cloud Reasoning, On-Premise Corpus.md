---
tags: [adr, mentorforge, architecture]
created: 2026-05-29
adr-number: ADR-001
status: accepted
supersedes: []
superseded-by: []
---

# (C) ADR-001 — Hybrid Architecture: Cloud Reasoning, On-Premise Corpus

> **Date:** 2026-05-29 | **Status:** Accepted
> **Supersedes:** — (foundational ADR; supersedes the cost-optimized cloud thesis captured in `(C) Architecture Sketch v1.md`)
> **Superseded by:** —

---

## Context

MentorForge is an open-source AI learning platform that teaches via Socratic mentoring over customer training documents. Customers deploy it via CDK into their own environments. Two forces shape the architecture:

1. **The buyer is enterprise.** L&D, compliance, onboarding, technical training — the customers who need a Socratic mentor at scale are large orgs with security, data residency, and governance requirements that disqualify "upload everything to a SaaS" approaches.
2. **The corpus is the most sensitive material in the org.** Training documents reference internal policies, customer cases, regulated data (PHI/PII/financial/IP), and tribal knowledge. The corpus *is* the crown jewels.

The architecture went through two earlier shapes before landing here:

| Iteration | Posture | Why it was rejected |
|---|---|---|
| v1 (cost-optimized cloud) | Lambda everywhere · Aurora pgvector · fck-nat · everything in AWS | Cheap to demo, but doesn't survive enterprise procurement. Corpus stored in AWS account is a non-starter for regulated industries. |
| v2 (enterprise cloud) | AgentCore + Bedrock KB + OpenSearch / Neptune Analytics | Solves the enterprise security posture, but still requires the customer's corpus to land in AWS. Limits the addressable market in healthcare, financial services, government, pharma, legal, and critical infrastructure. |
| **v3 (hybrid)** | **AgentCore + Bedrock in cloud · GraphRAG + Neo4j + Ollama on-prem** | **Chosen.** |

The wedge sentence:
> Most enterprise AI platforms ask you to upload your most sensitive training material to a third-party cloud to teach your employees. MentorForge doesn't. The reasoning happens in the cloud; the corpus never leaves your datacenter.

This ADR locks in the data-residency boundary as the foundational architectural primitive everything else flows from.

---

## Options Considered

### Option A — Full cloud, Bedrock-native (v2 architecture)

**Shape:** AgentCore + Bedrock KB + Neptune Analytics GraphRAG. Customer uploads corpus to S3 in their AWS account; KB ingests, embeds, builds the graph; AgentCore Gateway calls `kb_retrieve`.

| Pros | Cons |
|---|---|
| Simplest architecture — one cloud, one IaC stack | **Corpus must be uploaded to AWS** — disqualifies regulated industries |
| Native AgentCore integration via standard Retrieve API | Cost floor ~$350/mo idle (Neptune Analytics) even for an empty system |
| Fully managed — no on-prem ops | Reviewers in healthcare / finance / gov will reject in procurement |
| AWS CB story is "enterprise on AWS-native primitives" | Story is *one of many* — doesn't differentiate from every other Bedrock-on-AWS platform |

### Option B — Full on-premise (no cloud dependency)

**Shape:** Everything self-hosted. Local LLM for reasoning (Ollama running Llama 3.3 70B), local GraphRAG, local frontend, local auth.

| Pros | Cons |
|---|---|
| Maximum data residency — zero data leaves the customer DC | Loses Bedrock Claude reasoning quality (Llama 3.3 70B is good but not Claude-Sonnet good) |
| Zero cloud cost | Loses AgentCore's managed runtime, memory, observability, identity primitives — would have to rebuild |
| Customer fully owns the stack | Massive ops burden on customer; CDK no longer helps |
| Open-source story is pure | Loses the differentiation of agentic primitives — becomes "another LangChain RAG app" |

### Option C — Hybrid: cloud reasoning, on-premise corpus (CHOSEN)

**Shape:**
- **AWS side**: Frontend, Cognito federation, AgentCore (Runtime + Memory + Gateway + Identity + Observability), Bedrock Claude.
- **On-premise side**: Microsoft GraphRAG (Full Standard mode) + Neo4j Community Edition + Ollama (entity-extraction LLM) + FastAPI MCP server, all in Docker Compose on a single VM.
- **Wire**: AgentCore Gateway calls an MCP-compatible HTTP tool on the on-prem service over an encrypted tunnel — Cloudflare Tunnel for demo, AWS Site-to-Site VPN for production.
- **Data flow**: Outbound = query strings only. Inbound = retrieved chunks + graph context (optionally PII-redacted at the on-prem boundary). Source documents never leave premise.

| Pros | Cons |
|---|---|
| **Corpus stays on-prem** — unlocks regulated industries (healthcare, finance, gov, pharma, legal, critical infra) | More moving parts — two deployment surfaces (CDK for AWS, Docker Compose for on-prem) |
| Keeps Bedrock Claude reasoning quality | Cross-boundary latency added to every retrieval (target: <300ms over wire) |
| Keeps AgentCore managed primitives | Wire reliability becomes a SPOF — needs HA pattern for production |
| OSS stack on-prem = $0 software cost | Customer must own VM ops (one VM, Docker Compose, manageable) |
| The data-residency story is the differentiation moat | More complex security review — two perimeters to defend |
| Same primitive (hybrid wire) is reusable for sibling project EOP | Newer integration pattern — fewer reference architectures to point at |
| Strong AWS CB content angle — contrarian, defensible | Hybrid debugging is harder than single-cloud debugging |

---

## Decision

We chose **Option C — Hybrid** because:

1. **Data residency is the moat.** Vector RAG over uploaded corpora is now a commodity. "Corpus stays on-prem, reasoning happens in cloud" is a genuine architectural differentiation that survives the next 5 years of competitive pressure.
2. **The addressable market expansion is non-negotiable.** Healthcare, financial services, government, pharma, legal, and critical infrastructure all have data residency requirements that disqualify full-cloud architectures. Option A walks away from these markets. Option C captures them.
3. **The trade-off costs are manageable.** The on-prem OSS stack adds operational complexity but no licensing cost. Cross-boundary latency is acceptable for a Socratic mentor whose generation time dominates retrieval time anyway. The wire SPOF is addressable with standard HA patterns.
4. **The reasoning quality stays high.** Option B forces a downgrade from Bedrock Claude to local LLM for the agent loop. Hybrid keeps the best-in-class reasoning model where the user experience lives.
5. **The primitive is reusable.** The on-prem GraphRAG + hybrid wire pattern transfers directly to the Enterprise Onboarding Platform project. One architectural primitive, two products = leverage.

The on-prem stack is locked as: **Microsoft GraphRAG (Full Standard mode) + Neo4j Community Edition + Ollama (Llama 3.3 70B or Qwen 2.5 72B) + FastAPI MCP server**, packaged as Docker Compose. Full Standard mode is chosen over LazyGraphRAG because the cost argument for LazyGraphRAG (avoiding expensive cloud LLM calls at ingestion) disappears when Ollama runs locally at zero API cost — and Full Standard mode returns a richer community graph with Global Search capability. Detailed component selection is captured in subsequent ADRs (graph store, LLM, ingestion mode, wire pattern).

---

## Consequences

### What becomes easier
- **Selling into regulated industries.** Procurement can confirm "no corpus leaves our DC" in 30 seconds — that's a one-question security review.
- **Pluggable retrieval backends.** The MCP tool contract (`graph_retrieve`, `graph_traverse`, `explain_path`) is stable. Swapping Microsoft GraphRAG for LightRAG or Neo4j-graphrag library is a Docker Compose change.
- **The AWS CB content angle.** "Why we built MentorForge as hybrid" is a contrarian, defensible post with concrete trade-off math. Strong CB application material.
- **Cross-project reuse.** EOP can adopt the same on-prem service contract.
- **Explainability story.** GraphRAG returns graph paths, which gives the Socratic mentor the ability to say "you don't grasp X yet, which depends on Y" — and *show* the dependency. Vector RAG can't do this.

### What becomes harder
- **Deployment.** Customer runs `cdk deploy` for AWS *and* `docker compose up` on a VM. Two surfaces, two ops models.
- **Debugging.** Cross-boundary traces require correlation IDs propagated through MCP and AgentCore Observability. Not free, but standard.
- **Wire HA.** Production deployments need redundant wires (active + standby VPN, or VPN + tunnel fallback). Demo can use single tunnel.
- **Initial setup friction.** Customer needs a VM with ≥40GB RAM (Llama 3.3 70B) or ≥16GB (smaller model). Documented in the README.

### What this decision closes off
- **A pure SaaS offering.** MentorForge cannot be sold as "sign up and upload your docs" — the on-prem half requires customer infrastructure. This is a deliberate choice; trying to be both SaaS and hybrid would split the architecture.
- **Bedrock KB / Neptune Analytics paths.** Both are now out of scope for MentorForge V1+. If a customer wants a fully-cloud variant, they'd have to fork.
- **Multi-tenant on the AWS side at the corpus level.** Each customer deploys their own stack; we don't share corpus storage across tenants.

### What changes if we revisit
A future ADR could supersede this if:
- AWS launches a "bring-your-own-key-and-VPC" Bedrock KB variant that genuinely keeps corpus indices in the customer VPC with no AWS-side replicas
- A regulated-industry customer pilot reveals that the wire latency or HA story doesn't hold up
- The market shifts and the differentiation value of on-prem corpus drops below the operational cost of the second deployment surface

---

## What Would Revisit This Decision

Specific conditions under which this ADR gets superseded:

1. **A reference customer in healthcare or finance ships production and reports** that the wire reliability or latency is a blocker → could trigger a move to edge-cached retrieval or on-prem agent reasoning.
2. **Bedrock launches a true "data sovereignty" mode** where customer corpus is provably never persisted in AWS and indices live in customer-controlled keys/locations → could collapse back to Option A.
3. **A regulator publishes guidance** that explicitly approves Bedrock-native architectures for regulated workloads with sufficient controls → could shift the calculus toward Option A for non-strict customers.
4. **The on-prem OSS GraphRAG stack stagnates** (Microsoft GraphRAG abandoned, Neo4j Community Edition loses graph features) → could trigger a swap of on-prem components without changing the hybrid thesis.
5. **A sibling architectural primitive emerges** (e.g., AWS Outposts + Bedrock fully replicating the on-prem story) → could simplify deployment while preserving the wedge.

---

## References

- Architecture sketch v1 (superseded): [[(C) Architecture Sketch v1]]
- Architecture diagrams: [[(C) Architecture Diagram v1.drawio]] → [[(C) Architecture Diagram v2.drawio]] → [[(C) Architecture Diagram v3.drawio]]
- ADR backlog: [[(C) ADR Backlog]]
- AWS Bedrock KB GraphRAG GA announcement (Mar 2025) — used in research to confirm the cloud-native alternative
- Microsoft LazyGraphRAG (Jun 2025) — evaluated and rejected in favour of Full Standard mode; LazyGraphRAG's cost advantage (skipping cloud LLM calls at ingestion) dissolves when Ollama runs locally at zero API cost
- Strategic content angle: feeds [[03 Plans/(C) AWS Community Builder Plan]] as the "hybrid architecture" post candidate
- Reusable primitive: same wire pattern applies to [[04 Projects/Enterprise Onboarding Platform/CLAUDE.md|EOP]]
