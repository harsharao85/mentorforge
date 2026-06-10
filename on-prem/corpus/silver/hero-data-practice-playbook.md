---
source: {system: confluence, instance: northstar-confluence, source_id: "DATA-001", connector_version: "1.0"}
provenance: {author: "Sarah Chen", owner: "Data Practice", ingested_at: "2026-05-01"}
classification: {sensitivity: internal, acl: [all-employees]}
content_meta: {type: methodology, title: "Data Practice Playbook", tags: [data, methodology, onboarding]}
---

# Northstar Consulting — Data Practice Playbook

**Owner:** Sarah Chen, Data Practice Lead
**Audience:** All Data practice staff and incoming consultants
**Last reviewed:** Q1 2026

---

## 1. Who We Are

The Data Practice at Northstar Consulting is an 80-person team organized into four delivery teams: Data Engineering, Analytics & BI, ML & AI, and Data Governance. We serve clients across Financial Services, Healthcare, Retail, and Energy.

Sarah Chen leads the practice. Ben Okonkwo manages the Data Engineering team and is the primary point of contact for staffing and onboarding new Senior Consultants joining active engagements.

---

## 2. Our Core Stack

- **Ingestion & orchestration:** Apache Spark on Databricks, with Airflow for legacy clients
- **Transformation:** dbt (preferred) or Spark SQL
- **Lakehouse:** Databricks Unity Catalog for multi-tenant clients; Delta Lake for single-tenant
- **Analytics:** Tableau, Looker, and Databricks SQL for governed BI
- **Governance:** Unity Catalog + Collibra; HIPAA/GDPR-scoped access via column-level masking
- **Cloud:** AWS (primary), Azure (50% of healthcare clients), GCP (occasional)

If you are joining a Databricks engagement, read the **Meridian Unity Catalog Retrospective** before your first client call. Dana Okafor led that migration and is the firm's go-to expert on Unity Catalog.

---

## 3. How We Run Engagements

| Phase | Duration | Lead | Output |
|---|---|---|---|
| Discovery | 2–4 weeks | Manager+ | Current-state assessment, data quality scorecard |
| Design | 2–6 weeks | Senior Consultant+ | Architecture decision records, pipeline design |
| Build | 6–16 weeks | Consultant+ | Working pipelines, tested and documented |
| Transition | 2–4 weeks | Manager | Runbooks, knowledge transfer, hypercare |

Consultants joining mid-engagement should request the **engagement runbook** from their engagement lead during their first week.

---

## 4. Healthcare Clients and HIPAA

Read the **HIPAA Handling Policy** on Day 1 if you are staffed on any healthcare engagement.

**Atlas-Health** is our flagship HIPAA engagement. If you are staffed on Atlas-Health, the **Atlas-Health Data Stack Runbook** is your first read — it covers environment access, data classification tiers, and who approves each level of access. Questions about HIPAA compliance on Atlas-Health → contact Lena Hofer.

---

## 5. New to the Practice? Start Here

**Week 1 reading list:** This playbook → HIPAA Handling Policy (if healthcare-staffed) → your engagement runbook → Meridian Unity Catalog Retrospective (Databricks clients only)

**People to know on Day 1:**
- Ben Okonkwo (Data Engineering Lead) — your manager or direct point of contact
- Your buddy — reach out before Day 1 if possible
- Sarah Chen, Practice Lead — open-door Thursday afternoons for new hires

Tom Rivera (Senior Consultant, Data Engineering) runs the bi-weekly pipeline review and actively welcomes new hires to sit in.

---

## 6. Ask Me About

- **Unity Catalog migrations:** Dana Okafor (Cloud practice) led the Unity Catalog migration on the Meridian engagement. Reach out to Dana for Unity Catalog setup, schema migration, or catalog governance.
- **HIPAA data engineering:** Ben Okonkwo and Lena Hofer for regulated-data pipeline design.
- **dbt at scale:** Tom Rivera can add you to the dbt working group.

---

## 7. Communities

- **Data Science Community** — cross-practice learning on ML, analytics, and data engineering. Meets monthly.
- **AI/GenAI Guild** — weekly Slack channel, monthly lunch-and-learn.
- Join via MentorForge → Communities, or ping Sarah Chen directly.
