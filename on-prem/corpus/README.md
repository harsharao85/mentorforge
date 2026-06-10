# MentorForge — Demo Corpus Assembly

Assembles the complete demo corpus for Northstar Consulting — hero docs + bulk generated docs — and stages it for GraphRAG Full Standard indexing.

## Prerequisites

1. **TASK-001 complete:** `on-prem/datagen/output/` must exist
2. **Cast patched:** `manifest.json` must contain `demo_cast` (run `patch_cast.py`)
3. **VM ready:** per the On-Prem Vector Store Readiness Checklist before the bake

## Quick start

```bash
cd on-prem/corpus
pip install -r requirements.txt

# 1. Patch the cast names into TASK-001 output (one-time)
python3 patch_cast.py

# 2. Assemble corpus → silver/ (fast offline run)
python3 seed_demo.py --no-llm

# 3. With Ollama for richer bulk docs (requires llama3.3 running)
python3 seed_demo.py --ollama-model llama3.3
```

## What gets assembled

| Source | Count | Where |
|---|---|---|
| Hero docs (hand-quality, demo-critical) | 15 | `hero/` → `silver/` |
| Bulk generated docs (policy, runbooks, FAQs, briefs) | 23 | `generated/` → `silver/_bulk/` |
| Provenance index (ADR-019 envelope) | 1 | `silver/_index.json` |

## Hero docs

The hero docs are the on-screen content that makes all 3 demo stories work:

| Doc | Story | Cast referenced |
|---|---|---|
| `data-practice-playbook.md` | 1 | Sarah Chen, Ben Okonkwo, Tom Rivera, Dana Okafor |
| `hipaa-handling-policy.md` | 1 | Lena Hofer, Atlas-Health |
| `atlas-health-data-stack-runbook.md` | 1 | Priya Nair, Ben Okonkwo, Lena Hofer, Dana Okafor |
| `how-we-run-data-engagements.md` | 1 | Priya Nair, Ben Okonkwo, Tom Rivera |
| `meridian-unity-catalog-retrospective.md` | **2** | **Dana Okafor, Unity Catalog, Meridian** |
| `cloud-migration-methodology.md` | 2 | Marcus Lee, Dana Okafor, Northwind |
| `navigating-your-first-90-days.md` | 3 | Aisha Rahman, Women in Tech, Newcomers ERG |
| `erg/women-in-tech.md` | 3 | Aisha Rahman, Priya Nair |
| `erg/newcomers.md` | 3 | Priya Nair, Marcus Lee, Aisha Rahman |
| `erg/cloud-guild.md` | 2 | Dana Okafor, Marcus Lee |
| `erg/data-science-community.md` | 1 | Ben Okonkwo, Tom Rivera, Priya Nair |

## Cast patch

`patch_cast.py` injects the demo cast into TASK-001's random-name output:

| Cast member | Role | Graph node |
|---|---|---|
| Priya Nair | New hire, Data, Vancouver | person-0371 |
| Marcus Lee | New hire, Cloud, Toronto | person-0370 |
| Aisha Rahman | New hire, Strategy, London | person-0373 |
| Sarah Chen | Data Practice Lead | (practice-data leader) |
| Ben Okonkwo | Priya's manager | (Priya's reports_to) |
| Tom Rivera | Priya's buddy | (Priya's buddy_of) |
| Lena Hofer | Atlas-Health engagement lead | (engagement-0002 lead) |
| Dana Okafor | Cloud, Unity Catalog expert | person-0076 |
| Jordan Chen | Cloud, opted-out (Story 2 consent demo) | (Cloud practice) |

Engagements: `Atlas-Health` (healthcare/HIPAA), `Northwind` (retail), `Meridian`, `Helios`.

## After assembly — GraphRAG bake

```bash
# Load TASK-001 org graph into Neo4j first
cypher-shell -u neo4j -p <password> -f ../datagen/output/load.cypher

# Copy corpus to GraphRAG input
docker cp silver/. mentorforge-graphrag-1:/app/input/

# Run Full Standard index (~hours on one VM)
docker exec mentorforge-graphrag-1 python -m graphrag index --root /app

# Validate (after bake)
docker exec mentorforge-graphrag-1 python -m graphrag query \
  --root /app --method global \
  --query "Who at Northstar Consulting knows Unity Catalog?"
```

## Story validation queries (post-bake)

```cypher
-- Story 1: Priya's Day 1 context
MATCH (p:Person {name: "Priya Nair"})-[:HAS_ROLE]->(r:Role)
MATCH (p)-[:MEMBER_OF]->(t:Team)-[:PART_OF]->(pr:Practice)
MATCH (p)-[:REPORTS_TO]->(mgr:Person)
MATCH (p)-[:BUDDY_OF]->(buddy:Person)
RETURN p.name, r.title, t.name, pr.name, mgr.name, buddy.name

-- Story 2: Dana's Unity Catalog expertise
MATCH (d:Person {name: "Dana Okafor"})-[:EXPERT_IN]->(s:Skill)
WHERE s.name CONTAINS "Unity"
MATCH (d)-[:MEMBER_OF]->(t:Team)-[:PART_OF]->(pr:Practice)
RETURN d.name, collect(s.name), pr.name, d.networking_opt_in

-- Story 3: Aisha's thin network
MATCH (a:Person {name: "Aisha Rahman"})
RETURN a.name, a.status, a.networking_opt_in, a.discoverable
```
