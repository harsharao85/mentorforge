---
source: {system: s3, instance: northstar-policy-bucket, source_id: "RUN-AH-2026-01", connector_version: "1.0"}
provenance: {author: "Lena Hofer", owner: "Atlas-Health Engagement", ingested_at: "2026-03-01"}
classification: {sensitivity: confidential, acl: [atlas-health-team]}
content_meta: {type: runbook, title: "Atlas-Health Data Stack Runbook", tags: [atlas-health, runbook, data, hipaa, databricks]}
---

# Atlas-Health Engagement — Data Stack Runbook

**Engagement Lead:** Lena Hofer  
**Data Engineering Lead:** Ben Okonkwo  
**Last updated:** March 2026  
**Audience:** Northstar team members onboarding to the Atlas-Health engagement

---

## 1. Engagement Overview

Atlas-Health is a US-based healthcare payer managing 4.2M members across 12 states. Northstar has been the strategic data engineering partner since 2024. The engagement's primary workstream is modernizing Atlas-Health's data platform from an on-premises Teradata warehouse to a cloud-native Databricks Lakehouse on AWS.

**Engagement lead:** Lena Hofer (lena-hofer at northstar-consulting.com)  
**Client data lead:** James Watkins (Atlas-Health, VP Data Architecture)  
**Northstar team:** ~14 consultants across Data Engineering (Ben Okonkwo's team) and ML & AI

This is a HIPAA-regulated engagement. Read the **HIPAA Handling Policy** before accessing any Atlas-Health environment.

---

## 2. Environment Access

### 2.1 Access Provisioning

All access requests route through Lena Hofer. Do not contact the client directly.

| System | How to request access | Approver | SLA |
|---|---|---|---|
| AWS Console (Atlas-Health account) | Access request form → Lena | Lena Hofer + Client | 2 business days |
| Databricks workspace | Same form | Lena Hofer | 1 business day |
| Atlas-Health VPN | IT support ticket (reference AH engagement) | Lena + IT | 3 business days |
| Confluence (shared AH workspace) | Self-serve via Lena invite | Lena | Same day |

New hires joining the engagement: Lena will initiate access provisioning on your first day. You will receive a calendar invite for the AH environment setup session (usually Day 2 or Day 3).

### 2.2 MFA Requirement

All Atlas-Health systems require MFA. Set up your MFA before requesting any system access. Questions → Lena Hofer or the IT helpdesk.

---

## 3. Data Architecture

The Atlas-Health data platform follows a medallion architecture on Databricks:

```
Bronze  (raw landing)   — Atlas-Health S3 (client-owned, PHI present)
Silver  (clean/conform) — Northstar S3 cross-account sync (de-identified Tier 2)
Gold    (aggregated)    — Databricks Unity Catalog (Tier 3, BI-ready)
```

**Key point:** Northstar only processes Tier 2 (de-identified) and Tier 3 (aggregated) data. All Tier 1 PHI transformations happen in the client's own AWS account, managed by their internal team. Our pipelines consume the output of their de-identification process.

### 3.1 Unity Catalog Setup

Atlas-Health uses Databricks Unity Catalog for multi-tenant data governance across three metastores (prod, dev, staging). The metastore structure is:

```
atlas_health_prod
├── bronze_raw/          # PHI (client-managed, read-only for Northstar)
├── silver_clean/        # De-identified (Northstar pipeline writes here)
│   ├── members/
│   ├── claims/
│   └── encounters/
└── gold_analytics/      # Aggregated (shared with Atlas Analytics team)
```

For questions about the Unity Catalog configuration or schema migration patterns, **Dana Okafor** (Cloud practice) is the firm-wide expert on Unity Catalog. Dana led the Unity Catalog setup on the Meridian engagement and knows the common failure modes. Ping her before making catalog-level changes.

---

## 4. Our Pipelines

### 4.1 Core Pipelines (owned by Northstar)

| Pipeline | What it does | Owner | Schedule |
|---|---|---|---|
| `claims_ingest` | Transforms de-identified claims to silver | Ben Okonkwo | Hourly |
| `member_conform` | Standardizes member enrollment records | Priya Nair (pending) | Daily 2am |
| `claims_aggregate` | Builds gold claims summary tables | Data Engineering | Daily 6am |
| `encounter_quality` | DQ checks on encounter records | Analytics & BI team | Post-silver |

Note: Priya Nair is onboarding as the new owner for `member_conform` as of this quarter. Ben Okonkwo is mentoring the handoff.

### 4.2 Monitoring

- Pipeline alerts go to the `#ah-data-ops` Slack channel (Northstar internal — no PHI in Slack)
- Client-visible dashboards are hosted in Databricks SQL
- SLA breaches → page Ben Okonkwo (PagerDuty)

---

## 5. Key Contacts Quick Reference

| Role | Name | Contact |
|---|---|---|
| Engagement Lead | Lena Hofer | lena-hofer at northstar-consulting.com |
| Data Eng Lead | Ben Okonkwo | ben-okonkwo at northstar-consulting.com |
| Client Data Lead | James Watkins | jwatkins at atlas-health.com |
| Compliance / BAA | GRC team | compliance at northstar-consulting.com |
| Unity Catalog questions | Dana Okafor | dana-okafor at northstar-consulting.com |

---

## 6. New Hire Checklist (Atlas-Health)

- [ ] Read HIPAA Handling Policy
- [ ] Request environment access via Lena Hofer
- [ ] Complete HIPAA Awareness Training (onboarding task)
- [ ] Attend AH environment setup session (Day 2/3)
- [ ] Shadow `claims_ingest` pipeline review with Ben
- [ ] Introduce yourself in `#ah-data-ops` Slack
- [ ] Add yourself to the team roster in Confluence

Your onboarding buddy (Tom Rivera) has been through this checklist and can answer questions about the Atlas-Health day-to-day.
