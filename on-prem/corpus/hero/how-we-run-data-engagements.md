---
source: {system: confluence, instance: northstar-confluence, source_id: "DATA-ENGAGE-001", connector_version: "1.0"}
provenance: {author: "Ben Okonkwo", owner: "Data Practice", ingested_at: "2026-04-01"}
classification: {sensitivity: internal, acl: [all-employees]}
content_meta: {type: methodology, title: "How We Run Data Engagements", tags: [data, methodology, delivery, consulting]}
---

# How We Run Data Engagements at Northstar

**Author:** Ben Okonkwo, Data Engineering Lead
**Reviewed by:** Sarah Chen, Data Practice Lead

---

## Overview

Required reading for all new consultants joining a data engagement within their first week. The core principle: every engagement looks different on the surface, but the underlying delivery engine is the same.

---

## 1. The Four Phases

### Phase 1 — Discovery (2–4 weeks)
Establishes shared understanding. Deliverable: **Discovery Findings deck.** If you join after discovery, request the deck from your engagement lead — it is the fastest way to understand context.

### Phase 2 — Design (2–6 weeks)
Translates findings into architecture decisions. Every significant decision is captured in an ADR. Deliverable: **Architecture Design Document,** approved before Build begins.

### Phase 3 — Build (6–16 weeks)
Teams work in 2-week sprints. Key norms:
- Code in Git, always
- Every pipeline has a README, an error log, and a monitoring alert
- Peer review on all PRs — no self-merges on client code
- pytest for Python; dbt tests for transformation logic

Ben Okonkwo uses a pull-request template that enforces these norms — ask him for a copy on Day 1.

### Phase 4 — Transition (2–4 weeks)
Deliverable: **Operations Handoff Package** — runbooks, architecture diagrams, access inventory, escalation contacts. Includes a 30-day hypercare period.

---

## 2. Your Role on an Engagement

**As an Analyst:** Support senior team members, own discrete data quality or pipeline tasks.
**As a Consultant:** Own pipelines end-to-end. Participate in client standups.
**As a Senior Consultant** (e.g., Priya Nair, joining Atlas-Health this quarter): Lead a workstream. Review Analyst and Consultant code. Manage a subset of the client relationship.

---

## 3. Communication Norms

- **Internal daily updates:** 3-bullet async update in the engagement Slack channel by EOD
- **No PHI in Slack** — applies to all healthcare engagements including Atlas-Health
- **Escalate early** — tell Ben Okonkwo about blockers the day you find them

---

## 4. Helpful People

| Name | Role | Best for |
|---|---|---|
| Sarah Chen | Practice Lead | Career, big-picture practice questions |
| Ben Okonkwo | Data Eng Lead | Day-to-day delivery, pipeline reviews |
| Tom Rivera | Senior Consultant | Practical how-to, code review buddying |
| Lena Hofer | Atlas-Health Engagement Lead | Atlas-Health-specific questions |
| Dana Okafor | Cloud practice, Unity Catalog expert | Databricks/UC architecture |
