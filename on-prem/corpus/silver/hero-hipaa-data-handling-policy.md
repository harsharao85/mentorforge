# HIPAA Data Handling Policy

**Owner:** GRC & Compliance Team | **Approved by:** Managing Partner | **Classification:** Internal — All Staff
**Effective:** 2026-01-01 | **Review cycle:** Annual | **Next review:** 2027-01-01

---

## Purpose

Northstar Consulting works with clients in healthcare, life sciences, and adjacent regulated industries. This policy establishes mandatory obligations for every Meridian employee who accesses, processes, or is exposed to Protected Health Information (PHI) in any form — directly or through client systems.

**This policy applies to you the moment you are staffed on a healthcare engagement.** Non-compliance is grounds for disciplinary action and may expose Meridian and its clients to regulatory penalties under HIPAA/HITECH.

---

## What is PHI?

Protected Health Information is any individually identifiable health information transmitted or maintained in any form. At Meridian, you may encounter PHI through:

- Client data extracts shared for analysis or pipeline development
- Access to client environments (EHRs, data warehouses, cloud platforms)
- Documents, screenshots, or sample records shared in project channels
- Verbal disclosures in client calls

PHI includes: names, dates (except year), geographic data smaller than state, phone/fax numbers, email addresses, Social Security numbers, medical record numbers, account numbers, biometric identifiers, full-face photographs, and any other unique identifying number or code.

**If you are unsure whether something is PHI, treat it as PHI until confirmed otherwise.**

---

## Your core obligations

### 1. Minimum necessary access
Access only the data required for your specific task. Do not explore datasets beyond your workstream scope. Do not download or export PHI to personal devices or non-approved tools.

### 2. No PHI in project collaboration tools
PHI must not appear in:
- Slack messages or channels
- Email (even internal Meridian email)
- Jira, Confluence, or any project management tool
- GitHub repositories, notebook cells, or pipeline code

Use synthetic or masked data for development and testing. Engage the client's data team to provision approved masked datasets.

### 3. Encryption at rest and in transit
All PHI processed by Meridian tooling must be encrypted at rest (AES-256 or equivalent) and in transit (TLS 1.2+). Do not provision unencrypted storage for client healthcare data under any circumstances.

### 4. Client environment access
All access to client healthcare environments must be:
- Provisioned through the client's official IAM process
- Logged (client retains audit rights)
- Revoked immediately upon engagement close or role change

Do not use personal credentials, shared accounts, or bypass MFA requirements in client environments.

### 5. Breach response
If you suspect or confirm a PHI breach or unauthorized disclosure:
1. **Stop work immediately** on the affected system or dataset
2. **Notify your Manager within one hour** — do not investigate alone
3. **Do not notify the client directly** — escalation follows Meridian's incident response protocol
4. **Document what you know** (timeline, data involved, how discovered) in writing

The GRC & Compliance team will manage HIPAA-mandated breach notification timelines (60-day regulatory deadline).

---

## Active healthcare engagements (as of 2026-04-01)

| Client | Engagement ID | Data Lead | Status |
|---|---|---|---|
| Jones, Bean and Burton Ltd | engagement-0002 | Lisa Hensley (Director) | Closed — data retained under DPA |
| Reid, Weber and Lin Corp | engagement-0005 | Gina Moore (Director) | Active |

If you are staffed on either of these engagements, complete the **Healthcare Engagement Induction** with your engagement lead within your first week on the project.

---

## Training requirement

All staff on healthcare engagements must complete:
- [ ] **HIPAA Essentials for Consultants** (LMS — 45 min, annual renewal)
- [ ] **Healthcare Engagement Induction** (1:1 with engagement lead, first week)
- [ ] **Acknowledgement of this policy** (HR system — sign on first day of healthcare staffing)

Non-completion within five business days of engagement start will trigger an escalation to your Manager.

---

## Questions

Contact the **GRC & Compliance Team** via `#compliance-help` or your engagement lead. Do not make independent judgments about borderline PHI situations — ask.

*This policy is reviewed annually. Changes are communicated via all-staff email and updated in the Policy Register.*
