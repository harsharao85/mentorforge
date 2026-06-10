---
source: {system: confluence, instance: northstar-confluence, source_id: "CLOUD-METH-001", connector_version: "1.0"}
provenance: {author: "Cloud Practice", owner: "Cloud Practice", ingested_at: "2026-03-15"}
classification: {sensitivity: internal, acl: [all-employees]}
content_meta: {type: methodology, title: "Cloud Migration Methodology", tags: [cloud, migration, aws, methodology, consultant]}
---

# Northstar Cloud Migration Methodology

**Owner:** Cloud Practice
**Related engagements:** Northwind (active), Meridian (completed)

---

## 1. Our Migration Framework

Five-stage cloud migration framework derived from AWS MAP and our delivery experience across 40+ migrations:

| Stage | Name | Duration | Gate output |
|---|---|---|---|
| 1 | Assess | 2–4 weeks | Readiness scorecard, workload inventory |
| 2 | Mobilize | 2–3 weeks | Landing Zone, tooling decisions, team onboarded |
| 3 | Migrate | 6–20 weeks | Workloads migrated, dependency-ordered |
| 4 | Optimize | 4–8 weeks | Cost, performance, security baselines met |
| 5 | Operate | Ongoing | Client team in seat, runbooks complete |

---

## 2. The 7 Rs: Workload Disposition

Every workload gets a migration strategy: Retire, Retain, Rehost, Relocate, Repurchase, Replatform, or Refactor. Rehost the commodity tier, Replatform the strategic tier, Refactor only where it creates competitive advantage.

---

## 3. The Northwind Engagement

Northwind is an active UK-based retail client migrating their e-commerce platform to AWS. Marcus Lee joined the Cloud team this quarter as a Cloud Consultant.

**Workload disposition for Northwind:**
- E-commerce monolith (JavaEE): Replatform to ECS Fargate + RDS Aurora
- BI and analytics warehouse: Replatform to Databricks on AWS
- Legacy CRM (Siebel): Retain (license constraint until 2027)
- Marketing automation: Repurchase to Salesforce Marketing Cloud

**Key constraint:** EU GDPR data residency — all customer PII must remain in `eu-west-1` (Ireland) or `eu-central-1` (Frankfurt).

**Current phase:** Mobilize (Landing Zone deployed; Marcus Lee onboarding to client environment this week).

Marcus Lee joining Northwind should: (1) request AWS console access via the engagement lead, (2) read the Northwind Dependency Map in Confluence, (3) attend the weekly migration sync (Thursdays, 10am ET / 3pm GMT).

---

## 4. Landing Zone Standards

Northstar deploys AWS Landing Zones using Control Tower + Account Factory:
- Management Account → Security OU (Log Archive, Security Tooling) + Production OU (Networking, Workload accounts) + Non-Production OU (Dev, Staging)

Do not deviate from this structure without a written ADR.

---

## 5. People to Know in the Cloud Practice

| Name | Expertise |
|---|---|
| Dana Okafor | Databricks on AWS, Databricks Unity Catalog |
| Platform Engineering team | CDK construct library, ECS patterns |
| Cloud Guild leads | AWS architecture, Terraform/CDK |

Cloud Guild meets every other Thursday at 12pm PST. Ask to be added — Marcus Lee and all consultants on cloud-native workloads should join.

---

## 6. Security Baseline

Before any engagement handoff: all S3 public access blocked, CloudTrail enabled, GuardDuty enabled, AWS Config deployed, no long-lived IAM user credentials.
