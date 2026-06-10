---
source: {system: s3, instance: northstar-policy-bucket, source_id: "POLICY-HIPAA-2025", connector_version: "1.0"}
provenance: {author: "GRC & Compliance Team", owner: "Security Practice", ingested_at: "2026-01-15"}
classification: {sensitivity: internal, acl: [all-employees]}
content_meta: {type: policy, title: "HIPAA Data Handling Policy", tags: [hipaa, compliance, healthcare, policy]}
---

# HIPAA Data Handling Policy — Northstar Consulting

**Version:** 3.2  
**Owner:** GRC & Compliance Practice  
**Effective:** January 1, 2026  
**Applicability:** All staff assigned to healthcare engagements; mandatory read for Atlas-Health, Blue Ridge Partners, Summit Health, and all payer/provider clients

---

## 1. Purpose

This policy establishes Northstar Consulting's requirements for handling Protected Health Information (PHI) and electronic PHI (ePHI) on behalf of HIPAA-covered entities and their business associates. Violations may result in civil and criminal penalties for both the individual and the firm.

All staff **must read this policy and acknowledge receipt** before accessing any healthcare client environment. Acknowledgement is tracked via the onboarding task system.

---

## 2. What Is PHI?

Protected Health Information is any individually identifiable health information — including name, date of birth, SSN, diagnosis codes, treatment records, or claims data — held by a covered entity or business associate.

**Examples of PHI you may encounter on healthcare engagements:**
- Claims files (member ID, procedure code, provider NPI)
- Enrollment data (name, date of birth, plan ID)
- Clinical encounter records
- Audit logs that contain member identifiers

If you are unsure whether a dataset contains PHI, treat it as PHI until confirmed otherwise by your engagement lead.

---

## 3. Atlas-Health Specific Requirements

Atlas-Health is a HIPAA-regulated healthcare payer. All Northstar staff on the Atlas-Health engagement operate as Business Associates under a signed BAA.

**Atlas-Health data classification tiers:**

| Tier | Description | Storage allowed | Sharing |
|---|---|---|---|
| Tier 1 — PHI | Direct member identifiers | Atlas-Health managed S3 only | BAA signatories only |
| Tier 2 — De-identified | HIPAA Safe Harbor de-identified | Northstar S3 (encrypted) | Internal team only |
| Tier 3 — Aggregated | No individual identifiers, ≥11 members per cell | Standard Northstar systems | Internal + client |

**Access provisioning:** Lena Hofer (Atlas-Health engagement lead) approves all Tier 1 and Tier 2 access. Do not request access directly from the client — all requests route through Lena.

---

## 4. Handling Rules

### 4.1 At Rest
- All PHI must be encrypted at rest using AES-256 (SSE-KMS on AWS, equivalent on Azure)
- PHI may not be stored on local laptops, personal drives, or unencrypted removable media
- PHI notebooks and analysis environments must run in the client's regulated cloud environment

### 4.2 In Transit
- TLS 1.2 or higher required for all PHI transmission
- Email is **not** an approved channel for PHI — use the client's secure file transfer system
- Slack is **not** approved for PHI — this includes screenshots, file uploads, and message text

### 4.3 Access
- Minimum necessary access: request only the dataset columns your work requires
- All access to Tier 1 data is logged; expect audit queries
- Multi-factor authentication (MFA) is mandatory for all Atlas-Health environment access
- Offboarding from the engagement triggers access revocation within 24 hours

### 4.4 Incident Reporting
- Any suspected PHI breach (lost device, unauthorized access, misdirected email) must be reported within **1 hour** to your engagement lead and the GRC team
- Do not attempt to investigate a breach yourself — report first
- Atlas-Health has a 24-hour breach notification obligation to HHS; our internal 1-hour window is designed to give Northstar time to assess before the clock starts

---

## 5. Training Requirements

| Requirement | Frequency | Who |
|---|---|---|
| HIPAA Awareness Training | Annual | All staff |
| Healthcare Engagement Onboarding | Per engagement | New joiner on healthcare client |
| Incident Response Drill | Semi-annual | Healthcare engagement teams |

Training is tracked in the onboarding system. Your Day 1 journey task list includes completing the HIPAA Awareness module.

---

## 6. Questions and Contacts

- **Policy questions:** GRC & Compliance team — `compliance@northstar-consulting.com`
- **Atlas-Health access and BAA questions:** Lena Hofer — lena.hofer
- **Incident reporting:** `security-incident@northstar-consulting.com` and your manager immediately

This policy is reviewed annually and whenever regulatory guidance changes. Version history is maintained in the Policy S3 bucket.
