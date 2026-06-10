---
tags: [adr, mentorforge, architecture, production]
created: 2026-06-08
adr-number: ADR-028
status: accepted
phase: production
supersedes: []
superseded-by: []
depends-on: [ADR-009, ADR-012, ADR-020, ADR-026]
---

# (C) ADR-028 — Feature Flag Management (AWS AppConfig)

> **Date:** 2026-06-08 | **Status:** Accepted | **Phase:** Production
> First entry on the [[01 Architecture/(C) Production Phase Backlog]]. Not required for the demo — a production capability.

---

## Context

Production needs to **enable/disable elements of the app at runtime, without a redeploy** — experience pillars, audience modes, an action-tool kill switch, model selection, gradual rollouts. Today the only flag is an ad-hoc CDK-context `generatorImpl` (mock|live) that requires `cdk deploy` to change. We want a real flag store + a management console for the production phase, consistent with the deploy-into-the-client's-own-account / data-residency model.

## Options Considered

| Option | Verdict |
|---|---|
| **AWS AppConfig Feature Flags** (Systems Manager) | **CHOSEN** — AWS-native, **in-account** (no external dependency / egress), CDK-provisionable, **AWS console as the management UI**, deployment strategies (gradual rollout), flag variants, **auto-rollback on a CloudWatch alarm**, Lambda extension + SDK retrieval. Cheap. |
| **CloudWatch Evidently** | **REJECTED — deprecated.** AWS ended support **Oct 16, 2025** and explicitly steers feature-flag use to AppConfig. Don't build on a dead service. |
| **LaunchDarkly / Split (SaaS)** | Rejected for V1 — external dependency + cost + data egress; conflicts with the in-account/residency ethos. Keep as an adapter option for clients already standardized on it. |
| **Unleash / Flagsmith (OSS self-host)** | Viable for air-gapped / non-AWS-native clients; adds a service to operate. Keep as the air-gapped alternative. |

## Decision

**AWS AppConfig** as the production feature-flag store + management console.

- **Provisioned via CDK** (ADR-012): AppConfig application → environment(s) → configuration profile (feature-flag type) → flags → deployment strategy. Wire a CloudWatch alarm for auto-rollback.
- **Server-side consumption:** Lambda via the **AppConfig Lambda extension** (cached, low-latency); the agent in AgentCore Runtime polls AppConfig.
- **Client-side (UI) flags:** the SPA is browser-side, so UI flags are **delivered to the SPA via a config endpoint / on WebSocket connect** (a server reads AppConfig and vends the UI-relevant subset). Don't try to give the browser direct AppConfig access.
- **Management = the AWS AppConfig console** (client ops). A **custom branded admin UI is out of scope for V1-prod** (possible later).
- **Migration quick-win:** formalize the existing `generatorImpl` ad-hoc context flag into AppConfig as the first flag — instant toggle + rollback replaces the redeploy.

## Initial flag catalog

Grouped by what they gate (start small; grow as elements are wired):

**Experience / product**
- `experience.onboarding` (on) · `experience.socratic_learning` (off — demo-deferred, ADR-020) — gate the second pillar.
- `ui.show_agent_machinery` — **the CIO-vs-HR audience toggle** (show/hide tool chips + thinking). *Client-side flag.*

**Agent / model**
- `agent.generator` = `mock | live` (formalizes the existing context flag).
- `model.reasoning` = `sonnet | haiku` (ADR-009 fallback / cost lever).
- `agent.streaming` = on/off (token streaming vs batch).

**Tools / actions (safety)**
- `tools.scheduling_enabled` + **`tools.action_kill_switch`** — instant disable of action tools if anything misbehaves. The single highest-value safety flag.
- `tools.graph_traversal_tier2` — gate Tier-2 graph tools for vector-only RAGs (ADR-026 R2 graceful degradation).

**Governance (as they land)**
- `consent.enforcement` (off → on when ADR-007 v1.1 consent ships).
- `memory.episodic` (off → on when ADR-023 ships).
- Per-org / per-tenant overrides (future multi-tenant).

## Consequences

- **Runtime toggles without redeploy**; gradual rollout + instant auto-rollback on alarm.
- Unlocks the **audience-configurable demo** (show/hide machinery) and a **safety kill-switch** for action tools — both genuinely useful, not just plumbing.
- Adds AppConfig to the stack (minor) + a **flag-delivery path to the SPA** (the one new bit of wiring).
- **Achievability:** standing up AppConfig + first flags is quick; wiring each element to a flag is incremental, proportional to flag count. A production capability — not on the demo critical path.

## What Would Revisit This

- Client standardizes on LaunchDarkly → build an adapter behind the same flag-read seam.
- Air-gapped client → Unleash/Flagsmith self-hosted on-prem.
- Need for experiment-grade analytics (A/B with stats) → pair AppConfig flags with a data-warehouse analysis path (AppConfig vends variants but does not analyze).

## Sources (validated 2026-06-08)

- [Support for Amazon CloudWatch Evidently ending soon](https://aws.amazon.com/blogs/mt/support-for-amazon-cloudwatch-evidently-ending-soon/) (EOL 2025-10-16; migrate to AppConfig)
- [Using AWS AppConfig Feature Flags](https://aws.amazon.com/blogs/mt/using-aws-appconfig-feature-flags/)
- [AWS AppConfig Feature Flags GA](https://aws.amazon.com/about-aws/whats-new/2022/03/aws-appconfig-feature-flags/)

---

*Part of the MentorForge architecture decision log. ADRs are append-only.*
