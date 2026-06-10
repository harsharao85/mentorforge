# Jones, Bean and Burton Ltd — Client Data Stack Runbook

**Engagement:** engagement-0002 | **Practice:** Data | **Status:** Closed (data retained under DPA)
**Engagement Director:** Lisa Hensley | **Senior Consultant:** Stephanie Salazar
**Classification:** Meridian Internal — Engagement Team Only | **Last updated:** 2026-03-15

---

## Engagement overview

Jones, Bean and Burton Ltd is a regional healthcare payer operating across four US states. Meridian was engaged to design and deliver a cloud-native data platform on AWS to consolidate claims, member eligibility, and provider data from three legacy on-premise systems.

**Delivered:** Databricks lakehouse (Unity Catalog) on AWS, Airflow-managed ingestion pipelines, dbt transformation layer, and Tableau reporting layer. Handover completed March 2026.

This runbook captures the architecture, access patterns, and tribal knowledge for future reference — particularly if Meridian re-engages for Phase 2.

---

## Stack at a glance

| Layer | Technology | Notes |
|---|---|---|
| **Raw ingestion** | AWS Glue + S3 (Bronze zone) | Three source connectors: claims, eligibility, provider |
| **Orchestration** | Apache Airflow (MWAA) | DAGs in `jbb-data-pipelines` GitHub repo |
| **Lakehouse** | Databricks on AWS | Unity Catalog; all tables registered in UC |
| **Transformation** | dbt Core | Models in `jbb-dbt` repo; full test coverage on Tier 1 tables |
| **Serving** | Databricks SQL Warehouse + Tableau | Embedded in client's Tableau Server instance |
| **Governance** | Unity Catalog + AWS Lake Formation | PHI tables tagged; column-level masking on PII fields |
| **Monitoring** | Databricks Lakehouse Monitoring + CloudWatch | SLA alerts wired to client's PagerDuty |

---

## PHI handling architecture

**Critical:** this engagement processes PHI (claims data contains member IDs, diagnoses, and dates of service). The following controls are non-negotiable:

- All PHI tables are in the `phi_controlled` Unity Catalog catalog — access requires explicit UC grant
- Column-level masking is applied to member SSNs and dates of birth in all serving-layer views
- No PHI leaves the client's AWS account boundary — Meridian tooling never held raw PHI
- Airflow logs are scrubbed of PHI before shipping to Meridian's observability stack

If Phase 2 re-engages on PHI data, the **HIPAA Data Handling Policy** governs immediately. Review with Lisa Hensley before accessing any client environment.

---

## Repository map

| Repo | Purpose | Primary author |
|---|---|---|
| `jbb-data-pipelines` | Airflow DAGs for raw ingestion | Stephanie Salazar |
| `jbb-dbt` | Transformation models (bronze→silver→gold) | Johnathan Davis |
| `jbb-infra` | Terraform for AWS infra | (Cloud practice handoff) |

All repos are in the client's GitHub Enterprise org. Meridian no longer has access post-handover; client IT can reinstate for Phase 2.

---

## Known complexity / gotchas

1. **Claims schema drift** — the legacy claims system has undocumented schema changes roughly quarterly. The Airflow DAG includes a schema-comparison step that alerts before loading. **Do not bypass this check.**
2. **Eligibility data lag** — member eligibility files arrive 48–72 hours after the effective date. Downstream models account for this with a lookback window; changing the window without understanding the business logic will break the member attribution model.
3. **Unity Catalog workspace binding** — the Databricks workspace is bound to a single AWS region. If the client expands to a second region (they mentioned this as a Phase 2 item), workspace binding architecture needs to be revisited.
4. **Tableau extracts** — three dashboards use Tableau extracts (not live queries) due to client IT policy. Extract refresh schedule is 6am EST daily. If the dbt run fails overnight, the extract will reflect stale data — client has a manual override documented in their ops runbook.

---

## Contacts (client side — for Phase 2 re-engagement only)

| Name | Role | Notes |
|---|---|---|
| David Chen | Head of Data & Analytics | Primary stakeholder; engaged, technically literate |
| Maria Reyes | Data Platform Lead | Day-to-day technical owner post-handover |
| IT Service Desk | `servicedesk@jbb-health.com` | Environment access requests |

*Do not contact client-side individuals directly — re-engagement must be initiated through the Meridian account team.*

---

## Lessons learned (capture for future healthcare engagements)

- **Unity Catalog + PHI:** UC column masking + Lake Formation row-level security is a robust pattern for healthcare. Recommend as standard for future PHI workloads.
- **Airflow on MWAA:** simpler ops than self-managed Airflow but slower DAG parsing at scale. Client's DAG count is manageable; re-evaluate if they exceed ~200 DAGs.
- **Client data literacy gap:** plan 2× as much time for stakeholder enablement as you think you need. The best platform in the world fails if the client team can't run it.

*This runbook is a Meridian internal document. Do not share with third parties. Questions: contact Lisa Hensley or Stephanie Salazar.*
