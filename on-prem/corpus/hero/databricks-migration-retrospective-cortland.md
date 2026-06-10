# Engagement Retrospective — Databricks Unity Catalog Migration
## Cortland Financial Services

**Engagement type:** Data Platform Migration | **Industry:** Financial Services
**Lead consultant:** Courtney Gonzalez, Senior Consultant (Data Engineering team)
**Engagement Director:** Derek Zuniga, Senior Manager
**Duration:** October 2025 – February 2026 | **Status:** Completed
**Classification:** Meridian Internal — Knowledge Base | **Published:** 2026-03-05

---

## What we were hired to do

Cortland Financial Services is a mid-size asset manager running a legacy on-premise analytics stack (SQL Server + SSRS). They engaged Meridian to migrate to Databricks on AWS with Unity Catalog governance — retaining all historical data, maintaining regulatory reporting continuity (SEC, FINRA), and enabling their quant team to run Python-based research workloads alongside their existing SQL analysts.

**Success criteria defined at kickoff:**
1. Zero loss of historical data (7 years of trade and position records)
2. All existing SSRS reports reproducible in Databricks SQL within ±0.01% on all financial figures
3. Unity Catalog governance live, with row-level security for front-office vs. back-office data segregation
4. Migration completed before Q1 2026 regulatory reporting cycle

We hit all four.

---

## What we learned — the real retrospective

### 1. Unity Catalog migration is a project inside the project

We scoped UC migration as a two-week workstream. It took six. Here is why:

**Workspace binding:** existing Hive metastore tables cannot be migrated to UC in-place. Every table must be cloned to a UC-managed location, re-pointed, validated, and the old location deprecated. Cortland had ~3,200 tables. Even with the UC Metastore Migration Utility, the validation step (row counts, schema diffs, sample spot-checks) was the long pole.

**What we'd do differently:** scope UC migration at 3–4× whatever feels right. Run the utility against a full inventory before committing to a timeline. If the client asks "can we skip UC for now?" the answer is no — retrofitting UC governance onto an ungoverned workspace is more expensive than doing it first.

**Who to ask:** Courtney Gonzalez led every UC migration decision on this engagement. She has built a reusable validation script (in the `#data-community` pinned resources) that cuts the spot-check time by ~60%.

---

### 2. Row-level security in UC requires a data model decision upfront

Cortland needed front-office users to see only their own book of business — a common requirement in financial services. Unity Catalog Dynamic Views handle this cleanly, but only if the data model includes a `business_unit` or `user_group` column at the fact level.

Cortland's legacy schema didn't. We spent three weeks in the gold layer adding a `portfolio_owner_id` column, backfilling seven years of data, and validating that the Dynamic View filters aligned with their access control matrix.

**What we'd do differently:** make row-level security requirements a discovery artefact, not a build-phase surprise. The access control matrix must be agreed before data modelling begins, not after.

---

### 3. Parallel CDC + migration is harder than sequential

To avoid a long freeze window (Cortland's regulatory reporting runs 24/7), we ran Change Data Capture from the legacy SQL Server in parallel with the bulk historical load. DMS CDC on SQL Server requires the source to have SQL Server Agent running and CDC enabled at the table level — neither was configured.

Two weeks of coordination with Cortland's DBA team to enable CDC on 40 tables (each requiring a SQL Server restart in a maintenance window, phased over ten nights).

**What we'd do differently:** check CDC enablement at source during discovery, not during build. Add it to the discovery checklist as a prerequisite, not an assumption.

---

### 4. Quant team validation was the fastest part

We expected quant validation (replicating their Python research notebooks on Databricks) to be contentious. It was the smoothest phase. Two reasons: (a) the quants were already Databricks users at a prior firm, and (b) we gave them a sandbox on Day 1 of Phase 2 and let them experiment while we were still building.

**What to replicate:** give technically sophisticated client users early sandbox access. Their feedback catches modelling decisions that would otherwise surface at UAT.

---

## What shipped

| Deliverable | Owner | Notes |
|---|---|---|
| Databricks workspace (Unity Catalog) | Courtney Gonzalez | 3,200 tables migrated and validated |
| DMS CDC pipelines (40 source tables) | Crystal Robinson | Replication lag <5 min steady-state |
| dbt transformation layer (bronze→gold) | Jennifer Collins | 180 models, 100% test coverage on Tier 1 |
| Row-level security (Dynamic Views) | Courtney Gonzalez | Front/back-office segregation validated |
| Databricks SQL dashboards (15 reports) | Data Analytics team | SSRS parity confirmed ±0.01% |
| Unity Catalog validation script | Courtney Gonzalez | Reusable — see `#data-community` |

---

## Reusable artefacts (available in the knowledge base)

- **UC Validation Script** (`uc_migration_validator.py`) — Courtney Gonzalez. Compares row counts, schema, and sample rows between Hive metastore and Unity Catalog. Cuts validation time significantly.
- **CDC Prerequisite Checklist** — Derek Zuniga. Checklist of SQL Server and AWS DMS requirements to confirm before scoping a CDC migration.
- **Row-Level Security Design Template** — Courtney Gonzalez. Access control matrix template and Dynamic View implementation pattern for regulated financial data.

---

## If you're about to run a Databricks migration

1. **Talk to Courtney Gonzalez first.** She has run three UC migrations now and has patterns that will save you weeks.
2. UC migration timeline: 3–4× your first estimate.
3. Discovery must include: CDC enablement status, metastore table count, access control requirements, and a stakeholder who can approve the access control matrix in week one.
4. Give technical client users sandbox access early.

*Retrospective author: Courtney Gonzalez. Reviewed by: Derek Zuniga. Published to Meridian knowledge base: 2026-03-05.*
