---
tags: [adr, mentorforge, architecture, production]
created: 2026-06-08
adr-number: ADR-026
status: accepted
supersedes: []
superseded-by: []
depends-on: [ADR-001, ADR-006, ADR-007, ADR-010, ADR-012, ADR-019, ADR-024, ADR-025]
---

# (C) ADR-026 — Production Deployment Architecture

> **Date:** 2026-06-08 | **Status:** Accepted
> **Purpose:** Demarcate the **POC/demo build** from the **production architecture**, so the open-source repo communicates both clearly. The demo proves the thesis on a lean stack; production is the shape an enterprise actually deploys. Both ship in one repo; the README must make the line unmistakable.

---

## Context

V1 (TASK-001…007) is a **POC/demo**: it proves browser → AgentCore → Gateway → wire → on-prem GraphRAG → streamed turn on real data, on the cheapest stack that's honest (Cloudflare quick-tunnel, single AWS account, our reference on-prem GraphRAG, SSE-S3 / SSM, Cognito Hosted UI).

Production is a **different deployment shape** for an enterprise client. The core architecture (ADR-001 hybrid thesis, AgentCore primitives, MCP contract) is identical — what changes is **deployment topology, the wire, security posture, and the on-prem assumption.** Leaving this implicit makes the repo read as a toy. This ADR makes it explicit and sets the production target.

**Core production assumption:** *the client already has an on-prem vectorized RAG.* MentorForge's product boundary is the **MCP tool contract (ADR-007/025)** — the client implements the three tools against their existing RAG; our on-prem GraphRAG stack ships as a **reference implementation** for POC and for clients without one.

---

## POC vs Production — the demarcation

| Dimension | POC / Demo (V1) | Production |
|---|---|---|
| **Deployment** | Single AWS account, `cdk deploy` from a dev machine | Client's **own member account** under their AWS Org OU, **inheriting parent SCPs**; multi-account scenario |
| **IaC delivery** | `cdk deploy` (dev) | **Parameterized CloudFormation template** — client inputs connection + config via stack parameters |
| **The wire** | Cloudflare quick-tunnel (ephemeral URL, dies on restart) | **Site-to-Site VPN** (baseline) or **Direct Connect** (high-throughput/low-latency) → stable **private** endpoint |
| **On-prem RAG** | Our reference GraphRAG (Neo4j + Ollama + MCP) | **Client's existing on-prem vectorized RAG**, behind the MCP contract; our stack = reference impl |
| **Encryption** | SSE-S3, SSM Parameter Store (ADR-003b, cost) | **KMS CMK** + **Secrets Manager** + rotation (ADR-019 prod delta) |
| **Edge security** | WAF on CloudFront (basic) | WAF + **GuardDuty + Macie + Security Hub + CloudTrail**, VPC endpoints (no public egress) |
| **Auth** | Cognito Hosted UI, single pool | **Cognito + enterprise IdP** via SAML/OIDC federation (ADR-010) |
| **Gateway inbound auth** | `AWS_IAM` (ADR-024) | `AWS_IAM` until a per-learner/multi-tenant consumer → **`CUSTOM_JWT`** (ADR-024 revisit) |
| **Consent** | Verbal (deferred) | **Enforced** at the MCP tool layer (consent filtering) |
| **Memory** | Within-session only | Durable per-user episodic memory (ADR-023, parked) |
| **Tenancy** | Single-tenant | Single-tenant per account (multi-account = isolation boundary) |

---

## Production architecture decisions

### 1. Multi-account, SCP-inheriting deployment
The AWS layer deploys into the **client's own member account**, which sits under their Organization OU and **inherits the parent org's SCPs**. Implications the stack must honor:
- **No management-account / org-level actions.** Nothing assumes Organizations, OU, or SCP-write permissions. The stack is self-contained within one member account.
- **SCP-compatible by design.** Tolerate common guardrails: region pinning (parameterize region, default `us-east-1`), mandatory-tag policies (tag every resource), mandatory-encryption policies (CMK everywhere — aligns with the prod encryption delta), and deny-lists on risky services.
- **Documented prerequisites.** The client enables what SCPs can't grant for us: Bedrock model access (Claude Sonnet inference profile), service quotas, and the VPN/DX attachment. The README lists these as deploy prerequisites.

### 2. Parameterized CloudFormation
CDK (ADR-012) synthesizes to a **CloudFormation template exposing `CfnParameter`s** the client fills in at deploy time — no code edits required:
- On-prem MCP endpoint (**private DNS / IP** reachable over the wire)
- VPN/DX connection details (customer gateway, BGP ASN, on-prem CIDRs) or an existing TGW/attachment id
- VPC / subnet / CIDR allocations
- Allowed region(s)
- Cognito / enterprise-IdP federation config (metadata URL, client ids)
- Bedrock model id / inference-profile ARN
- MCP bearer secret reference (Secrets Manager ARN)

The repo publishes the **synthesized template** so a client can deploy via the CloudFormation console/CLI with parameters, in addition to `cdk deploy` for those who prefer it.

### 3. The wire — S-S VPN / Direct Connect (no tunnel)
Production replaces the Cloudflare quick-tunnel (ADR-006 already designated VPN for prod). The **AgentCore Gateway `mcpServer` target points at a stable private endpoint** (private DNS over VPN/DX) — which **eliminates the ephemeral-URL/restart problem** that bites the demo. 
- **Baseline:** Site-to-Site VPN (dual-tunnel for HA).
- **High-throughput / low-latency / steady-state:** Direct Connect, optionally with a VPN backup tunnel.
- Private-only: the on-prem RAG is never exposed publicly; the MCP endpoint resolves over the private link only.

### 4. Bring-your-own on-prem RAG
The **MCP tool contract (ADR-007 + v1.1 ADR-025) is the integration seam and the product boundary.** In production the client implements `graph_retrieve` / `graph_traverse` / `explain_path` against **their existing on-prem vectorized RAG**. Our GraphRAG stack (Neo4j + Ollama + GraphRAG) ships as a **reference implementation** — usable as-is for clients without a RAG, or as the spec to conform to. This keeps the corpus/vectors on-prem (ADR-001 invariant) while making the cloud layer RAG-agnostic.

### 5. Production hardening deltas
Re-introduce what the demo stripped for cost (ADR-003b) plus enterprise controls:
- **KMS CMK** (S3, DynamoDB, logs) + **Secrets Manager** with rotation (MCP bearer, IdP secrets)
- **WAF** (CloudFront + API GW), **GuardDuty**, **Macie**, **Security Hub**, **CloudTrail**
- **VPC endpoints** for AWS APIs (no public egress); private subnets only
- Least-privilege IAM; Gateway inbound → `CUSTOM_JWT` when per-learner/multi-tenant (ADR-024)
- Cross-boundary observability (ADR-013) wired through

---

## README requirement (launch artifact)

The repo `README.md` must carry a **"POC vs Production"** section using the demarcation table above, plus:
- A one-line architecture diagram for each (demo vs prod wire/account topology)
- **Production deploy prerequisites** (own account under Org, SCP compatibility notes, Bedrock access, VPN/DX attachment, BYO-RAG-behind-MCP-contract)
- The parameter list for the CloudFormation template
- Explicit statement: *"The demo runs on a Cloudflare tunnel + our reference GraphRAG; production runs over S-S VPN/Direct Connect against your own on-prem RAG, deployed into your own AWS account."*

*(Updating `README.md` is a launch-phase task and a non-`(C)` file — needs Harsha's go-ahead before editing.)*

---

## Consequences

- **The repo tells a real story:** a runnable demo *and* a credible enterprise deployment model — strong for OSS adoption and for the CB narrative.
- **RAG-agnostic cloud layer:** the MCP contract as the product boundary means MentorForge isn't married to our GraphRAG choice — it plugs onto whatever the client runs.
- **Harder:** maintaining two deployment paths (demo CDK + parameterized prod template) and keeping the README demarcation honest as the build evolves.
- **Closes off:** "just run our whole stack" as the only path — production explicitly assumes BYO-RAG.

## What Would Revisit This

- A client wants a **fully-managed** offering (we run the on-prem side) → a hosted variant, different residency story.
- **Multi-tenant** within one account demanded → revisit the single-tenant-per-account isolation model (and Gateway auth → CUSTOM_JWT).
- Air-gapped / classified client → ADR-018 (on-prem reasoning LLM too — major shift).

---

## Enterprise-Architect Review & Remediation (2026-06-08)

A first-principles EA pass over the first-cut sections above surfaced material gaps. Remediations and an open-risk register follow. *(Appended per review — original sections retained above; this layer adds depth and flags risks, it does not reverse decisions.)*

### R1 — Hybrid connectivity reality (the wire is more than "VPN/DX")
- **AgentCore Gateway → on-prem private reachability is the #1 open risk.** The demo worked because Gateway called a *public* HTTPS URL. A private VPN/DX endpoint is only reachable if Gateway can egress into the customer VPC. If it's managed-public-egress-only, production needs one of: (a) **PrivateLink / VPC interface endpoint** fronting the MCP service, (b) a **private NLB/ALB + API** in the customer VPC on a VPC-attached path, or (c) a thin **in-VPC relay** the Gateway calls. **Validate before committing the prod wire** (Risk Register RR-1).
- **Hybrid DNS:** Route 53 Resolver **inbound/outbound endpoints** to resolve on-prem private names. Without it the "private endpoint" can't be named.
- **CIDR planning:** non-overlapping VPC CIDRs vs on-prem and peer accounts; **Transit Gateway** (not VGW) for multi-VPC/account; surfaced as template params.
- **HA:** dual-tunnel VPN is HA; a **single Direct Connect is not** — real DX HA = redundant connections (two locations) or DX + VPN backup.

### R2 — BYO-RAG contract tiers (resolves the ADR-025 ↔ ADR-026 tension)
- **Tier 1 — Retrieval (any RAG):** `graph_retrieve` (+ filters). Vector-only RAGs implement this.
- **Tier 2 — Graph (graph RAG only):** `graph_traverse`, `explain_path(path_between)` — the people/why differentiator. **Degrade gracefully** if absent (agent falls back to retrieval; "who/why" beats narrate).
- Ship a **conformance kit** (test suite the client runs against their impl) + per-tool latency SLOs. Contract is text-in/results-out — embedding-agnostic.

### R3 — Landing-zone integration (don't duplicate centralized security)
- Member-account security services (**GuardDuty/Security Hub/Config**) become **parameterized/optional** — default to *integrate with the org-delegated admin*, not provision new.
- Ship CloudTrail + flow logs to the **client's central log-archive account** (param: bucket/role).
- **Cross-account deploy role** for the client's CI/CD to assume into the member account (least-privilege, documented).

### R4 — Data governance & compliance (the moat, made real)
- **Classification:** corpus/vectors = on-prem (ADR-001). **Learner interaction memory = PII on AWS** — the one personal-data flow to the cloud. Classify, CMK-encrypt, govern.
- **Lifecycle:** retention + **right-to-be-forgotten** (per-learner deletion) + data-access audit.
- **Frameworks (posture):** HIPAA (AWS **BAA**, eligible services only), SOC 2, GDPR; FedRAMP path for gov. Document in-scope/eligible services.
- **Keys:** customer-managed **CMK**, **BYOK** option.
- **Cross-ref:** episodic memory (ADR-023) **cannot stay parked for production** — it *is* the PII surface. **Production gates on ADR-023.**

### R5 — Reliability, DR, SLOs
- Define **SLO / RTO / RPO** (fill with client).
- **Degradation:** wire or on-prem RAG down → graceful "knowledge source unavailable," not a hang (extends TASK-005 error hardening to the wire).
- **Backup:** DynamoDB PITR; on-prem RAG backup is the client's, stated as a requirement.

### R6 — Scale, capacity & FinOps
- Dimensions: **Bedrock TPS/quota**, Lambda/AgentCore concurrency, DynamoDB capacity mode, on-prem RAG sizing (client req).
- **Cost model:** per-learner token economics, **cost-allocation tags**, budgets + anomaly alerts — where the project's "transparent cost" promise lands.

### R7 — Day-2 operations & supply chain
- **Runtime image lifecycle:** ownership, **ECR image scanning**, base-image patch cadence, **SBOM + image signing**.
- **Upgrade path:** versioned template + migration notes; **drift detection** (CFN drift / Config rules).

### R8 — Threat model & DLP
- **Threat-model the MCP boundary** (crown jewel): bearer-token rotation, **mTLS on the wire** (ADR-006), least-privilege Gateway role.
- **Prompt injection is acute** — the agent ingests corpus content **and holds action tools (scheduling)**. A poisoned doc could attempt to drive an action. Mitigate: tool-use guardrails + **HITL on all actions** (already mandated, ADR-008) + input provenance.
- **Boundary DLP:** promote optional **ADR-014** (PII redaction at the on-prem boundary) to **prod-required** for regulated clients.

### R9 — Licensing (enterprise legal)
Reference impl carries **Neo4j Community = GPLv3** and the **Llama community license** — document commercial-use implications; note Neo4j Enterprise / alternative-store paths. Our code stays MIT.

### Open Risk Register — validate before prod commit

| # | Risk | Severity | Action |
|---|---|---|---|
| RR-1 | ~~AgentCore Gateway may not reach a **private** VPN/DX endpoint~~ | ~~Blocker~~ → **RESOLVED 2026-06-08** | ✅ Validated: Gateway supports private egress via **VPC Lattice `privateEndpoint`** → TGW/VGW → DX/VPN. See [[01 Architecture/(C) ADR-027 — Hybrid Connectivity & AgentCore Gateway Private Egress]]. |
| RR-2 | Graph-typed tools unusable on a vector-only client RAG | High | Tier the contract (R2) + conformance kit |
| RR-3 | Episodic memory (PII) residency/compliance unresolved | High | Production gates on ADR-023 |
| RR-4 | Duplicating org-centralized security in member account | Medium | Parameterize/integrate (R3) |
| RR-5 | Single-DX assumed HA | Medium | Redundant DX or DX + VPN |
| RR-6 | Demo retrieval filters are **query-layer** because corpus chunks carry no structured metadata — production filtering must be metadata-driven, not heuristic | Medium | Backfill `role`/`practice`/`engagement`/`stage` into the **ingestion silver envelope** (ADR-019); filter on metadata at retrieval. Surfaced building TASK-007. |

### Follow-up ADRs this review spawns
- **ADR-027** — Hybrid connectivity & AgentCore private reachability (resolves RR-1)
- **ADR-023** — Episodic memory model — **un-park for production** (PII/residency)
- **ADR-014** — Boundary PII redaction — promote optional → prod-required
- Compliance matrix · DR/SLO · FinOps may each warrant their own ADR as the first enterprise engagement firms requirements.

---

*Part of the MentorForge architecture decision log. ADRs are append-only — supersede or refine, don't edit in place.*
