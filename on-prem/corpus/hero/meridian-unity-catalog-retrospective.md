---
source: {system: sharepoint, instance: northstar-sharepoint, source_id: "RETRO-MER-UC-2025", connector_version: "1.0"}
provenance: {author: "Dana Okafor", owner: "Cloud Practice", ingested_at: "2026-02-15"}
classification: {sensitivity: internal, acl: [all-employees]}
content_meta: {type: methodology, title: "Meridian Unity Catalog Migration Retrospective", tags: [databricks, unity-catalog, cloud, migration, retrospective, data-governance]}
---

# Meridian Engagement — Unity Catalog Migration Retrospective

**Lead Architect:** Dana Okafor, Cloud Practice  
**Engagement:** Meridian (Technology client — data platform modernization)  
**Migration completed:** Q4 2025  
**Document type:** Post-engagement retrospective — lessons learned for future Unity Catalog migrations

---

## Executive Summary

The Meridian engagement delivered a full migration from Databricks workspace-level Hive metastore to Unity Catalog (UC) across three production workspaces and two development environments. The migration took 14 weeks (planned: 10). The scope creep and delays were almost entirely avoidable — which is why this retrospective exists.

**If you are setting up Unity Catalog on a new engagement, read this document before you start schema design.** The three mistakes described in Section 3 each cost us at least a week. Combined, they accounted for all of the schedule slip.

---

## 1. What We Migrated

| Workload | Tables | Data volume | Migration strategy |
|---|---|---|---|
| Analytics warehouse | 340 tables | 8 TB | Lift-and-shift to `meridian_prod` metastore |
| ML feature store | 120 feature tables | 2 TB | Re-registered with UC feature engineering API |
| Streaming pipelines | 18 Delta Live Tables | Real-time | Recreated in new UC-enabled DLT workspace |

**Team:** Dana Okafor (lead architect), two Cloud practice consultants, and two Meridian data engineers.

---

## 2. What Went Well

### Unity Catalog governance capability
UC's row-level security and column-level masking are genuinely powerful for a regulated client like Meridian. Once set up correctly, the access controls were auditable in a way the old Hive metastore never was. The client's compliance team was visibly relieved.

### External Locations vs Managed Tables decision
We made the right call early to use **Managed Tables** for analytics workloads and **External Locations** only for streaming pipeline checkpoints. Clients who try to manage everything as External Locations end up maintaining a shadow infrastructure of S3 bucket policies that duplicates UC grants. Don't do it.

### Metastore topology
We used a single metastore per region with catalog-level separation (prod / dev / staging). This is simpler to govern than multi-metastore topologies for a single-tenant client.

---

## 3. What Went Wrong (The Three Mistakes)

### Mistake 1: Service Principal proliferation

**What happened:** We created a new service principal for each pipeline team (3 teams × 2 environments = 6 SPs). By week 6, we had 18 SPs and lost track of which SP owned which external location.

**Fix:** One service principal per environment role (read-only, write, admin). Names should encode the role: `sp-meridian-prod-write`, not `sp-pipeline-team-alpha`. We cleaned this up in week 8. It cost 3 days.

**For your next engagement:** Define SP taxonomy in your first ADR. Don't let teams create their own.

### Mistake 2: Delta sharing before UC governance was stable

**What happened:** Meridian wanted to share the analytics catalog with a partner firm using Delta Sharing. We set this up in week 4, before the column-level masking policies were finalized. The partner saw unmasked columns that should have been masked.

**Fix:** Governance policies must be finalized and tested **before** any Delta Sharing recipients are added. The sequence is: (1) UC governance locked, (2) e2e masking test, (3) Delta Sharing enabled.

**For your next engagement:** Gate Delta Sharing on a governance sign-off milestone. Do not let it run in parallel.

### Mistake 3: Migration of legacy UDFs without compatibility check

**What happened:** The Meridian analytics warehouse had 47 Hive-era UDFs registered in the old metastore. We migrated them to Unity Catalog without testing for Photon compatibility. 12 UDFs broke.

**Fix:** Run `SHOW USER FUNCTIONS` and test every UDF in a UC development workspace before migrating. Photon rejects anything relying on Hive SerDes. Budget 2–3 days for UDF validation on any engagement with legacy Hive workloads.

---

## 4. Recommended Migration Sequence

Based on Meridian, the sequence that minimizes risk:

1. **Assessment** (1 week): inventory workloads, SPs, storage locations, UDFs
2. **UC workspace setup** (1 week): metastore, catalogs, storage credentials, external locations
3. **Governance design** (1–2 weeks): row/column security, tag taxonomy, SP taxonomy — get sign-off
4. **Development migration** (2–3 weeks): migrate dev workloads, test everything, validate UDFs
5. **Production cutover** (1–2 weeks per workload tier): analytics first, streaming last
6. **Delta Sharing** (post-governance lock): only after step 3 is fully signed off
7. **Decommission Hive metastore** (after 30-day parallel run): archive old metastore, update all job references

---

## 5. Who to Call

**Dana Okafor** is the primary point of contact for any Unity Catalog engagement questions across the firm. She is listed in the skills directory as "ask me about: Databricks Unity Catalog."

Specifically, reach out to Dana if you are:
- Designing the metastore topology for a new UC migration
- Deciding between Managed Tables and External Locations
- Running into Delta Sharing governance questions
- Dealing with a SP proliferation problem (she has a cleanup runbook)
- Hitting Photon compatibility issues with legacy UDFs

---

## 6. Resources

- [Databricks Unity Catalog documentation](https://docs.databricks.com/en/data-governance/unity-catalog/index.html)
- Northstar internal: SP naming standards (Cloud Guild wiki)
- Northstar internal: Delta Sharing governance checklist (Cloud practice Confluence)
- Northstar internal: the cleanup runbook Dana wrote (ask her directly)
