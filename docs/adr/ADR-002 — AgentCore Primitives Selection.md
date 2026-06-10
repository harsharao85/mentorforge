---
tags: [adr, mentorforge, architecture]
created: 2026-05-30
adr-number: ADR-002
status: accepted
supersedes: []
superseded-by: []
extends: ["ADR-001"]
---

# (C) ADR-002 — AgentCore Primitives Selection

> **Date:** 2026-05-30 | **Status:** Accepted
> **Supersedes:** — | **Superseded by:** —
> **Extends:** [[(C) ADR-001 — Hybrid Architecture - Cloud Reasoning, On-Premise Corpus|ADR-001]]

---

## Context

ADR-001 locked the hybrid thesis: the reasoning brain runs in AWS, the corpus stays on-prem. This ADR decides **what the reasoning brain is built on** — the agent runtime and its supporting primitives shown in the AGENT LAYER of [[(C) Architecture Diagram v4.drawio|the v4 diagram]].

Six forces shape the choice:

1. **The agent calls on-prem tools over a wire.** It must invoke an MCP server across the data-residency boundary with auth — that needs a governed tool gateway, not ad-hoc HTTP calls baked into agent code.
2. **Onboarding takes actions on the learner's behalf.** Scheduling a meeting means acting as the user against a third-party calendar (Google / M365). That requires delegated identity + an OAuth token broker — building one safely is non-trivial.
3. **Both experience pillars need durable memory.** Session continuity (short-term) plus learner/onboarding state (long-term) across turns.
4. **Turns are long and streaming.** A turn does multiple tool round-trips over the wire *then* generates — it must stream and must not be capped at 30s (the failure mode ADR-021 fixes on the transport side; the runtime side must match).
5. **It ships OSS and deploys via CDK into the customer's account.** Minimize bespoke, always-on agent infrastructure the customer has to operate.
6. **AWS Community Builder narrative.** "Built on AgentCore primitives" is a sharper, more current content angle than "another LangChain app on Lambda."

---

## Options Considered

### Option A — Bedrock AgentCore managed primitives (CHOSEN)

Runtime + Memory + Gateway + Identity + Observability, with the agent code (Strands / LangGraph / CrewAI — framework-agnostic) hosted inside the Runtime.

| Pros | Cons |
|---|---|
| `InvokeAgentRuntime` streams, isolates each session in a microVM, supports sessions up to 8h — removes the long-turn / timeout problem | Newer service — CDK / CloudFormation coverage is partial; provisioning mixes CDK with control-plane APIs / starter toolkit |
| Identity gives **inbound** JWT validation + **outbound 3LO + Token Vault** — the calendar action surface becomes tractable without building an OAuth broker | Region availability must be confirmed before build |
| Gateway turns the on-prem MCP server into governed, auth'd tools (read graph tools + calendar action tools register here) | Some coupling to AWS-managed agent primitives |
| Memory replaces a hand-rolled learner-state store; scoped by actor/session | Less low-level control than self-hosting |
| Managed scaling/streaming = little always-on agent infra for the customer to run | |
| Strongest CB content angle | |

### Option B — LangGraph / LangChain agent on Lambda or Fargate

Self-managed: agent on Lambda (or Fargate for long turns) + DynamoDB for memory + a custom MCP client + a self-built OAuth token vault for the calendar delegation.

| Pros | Cons |
|---|---|
| Maximum control; no dependency on a newer managed service | Rebuilds four primitives by hand — memory, tool gateway/auth, delegated identity, observability |
| Mature CDK constructs for Lambda/DynamoDB/Fargate | **The outbound OAuth token vault is the dangerous part** — storing third-party user tokens securely is exactly what we shouldn't hand-roll |
| Familiar | Lambda's 15-min cap / cold starts vs long streaming turns; Fargate is always-on cost |
| | Weakest differentiation — "another RAG-agent on Lambda" |

### Option C — Self-built orchestration on ECS / EKS

Full custom agent loop + state machine on container infra.

| Pros | Cons |
|---|---|
| Total control; portable off AWS | Heaviest ops burden — defeats the one-command-deploy goal |
| | Everything in B's cons, plus cluster management |

---

## Decision

**Adopt Bedrock AgentCore.** Each primitive earns its slot — we are not adopting the suite wholesale for its own sake:

| Primitive | Why it earns its slot | What we'd otherwise build |
|---|---|---|
| **Runtime** | Streaming `InvokeAgentRuntime`, microVM session isolation, sessions to 8h. Framework-agnostic — our agent code stays portable. Matches the long, streaming turn (ADR-021). | Fargate service + custom session/streaming plumbing |
| **Memory** | actor/session-scoped short-term + long-term strategies for onboarding/learner state. | DynamoDB schema + retention + extraction logic |
| **Gateway** | MCP-native — the on-prem FastAPI MCP server plugs straight in; central place to register READ graph tools + ACTION calendar tools with auth. | Custom MCP client + per-tool authz |
| **Identity** | Inbound: validate Cognito JWT, bind the learner. **Outbound: 3LO + Token Vault** → the calendar scheduling action acts as the user. This single primitive is why onboarding's action surface is feasible. | A bespoke, security-sensitive OAuth token broker |
| **Observability** | OTel / X-Ray traces, per-turn cost + tool latency, correlation IDs across the wire (ADR-013). | Custom tracing + cost attribution |

The agent **code** running inside the Runtime stays framework-portable (Strands or LangGraph), and the on-prem tool contract is **standard MCP** — so the lock-in is to managed *hosting*, not to a proprietary agent model. That keeps the exit cost bounded.

---

## Consequences

### What becomes easier
- No always-on agent compute for the customer to operate; managed streaming + scaling.
- The act-on-behalf-of-user scheduling story (Identity outbound) — the hardest part of the onboarding pillar — is a configured primitive, not a security project.
- The on-prem MCP server registers as Gateway tools with minimal glue.
- A clean, current CB narrative.

### What becomes harder
- **Provisioning is not pure CDK.** Expect a split: CDK for VPC / IAM / Cognito / API Gateway / Lambdas / budgets (TASK-001), and the `bedrock-agentcore` control-plane APIs / starter toolkit / CLI for the AgentCore resources themselves. ADR-012 (CDK structure) must account for this seam.
- **Region availability is a gate.** Confirm AgentCore + the chosen Claude Sonnet model (ADR-009) are GA in us-east-1 before TASK-003.
- Debugging spans managed primitives — observability discipline (ADR-013) matters more.

### What this decision closes off
- The v1-era **DynamoDB learner-state store** and the **Python module-loader** pluggability idea — superseded. Pluggability now lives in the **agent definition** (ADR-008); state lives in AgentCore Memory.
- A hand-rolled OAuth token vault.

### What changes if we revisit
- If AgentCore pricing / limits / region coverage don't fit, fall back to Option B (LangGraph on Fargate) — the portable agent code + MCP contract make that a contained migration, not a rewrite.

---

## What Would Revisit This Decision

1. AgentCore pricing or quota limits prove incompatible with the per-turn cost model.
2. A customer requires an **air-gapped** deployment (no AWS) → on-prem reasoning LLM (ADR-018) — AgentCore drops out entirely.
3. CDK / CloudFormation coverage for AgentCore never matures and the provisioning friction outweighs the managed benefits.
4. A framework we want to standardize on can't run inside the Runtime.

---

## References

- [[(C) ADR-001 — Hybrid Architecture - Cloud Reasoning, On-Premise Corpus|ADR-001]] — hybrid thesis this extends
- [[(C) ADR Backlog]] — feeds ADR-007 (MCP tool contract), ADR-008 (agent definition), ADR-009 (reasoning LLM), ADR-013 (cross-boundary observability)
- [[(C) ADR-021 — WebSocket Experience Transport & Signal Protocol|ADR-021]] — the transport side of the long-streaming-turn requirement
- [[(C) Architecture Diagram v4.drawio]] — AGENT LAYER
- AWS docs (verified 2026-05-30): `InvokeAgentRuntime` streaming + 8h microVM sessions; AgentCore Identity inbound/outbound 3LO + Token Vault
- Strategic content angle: feeds [[03 Plans/(C) AWS Community Builder Plan]]
