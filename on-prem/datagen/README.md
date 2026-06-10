# MentorForge — Synthetic Org/People Graph Generator

Generates a synthetic IT-services/management-consulting org matching
[Graph Schema v2](../../01%20Architecture/%28C%29%20Graph%20Schema%20v2%20%E2%80%94%20Employee%20Experience%20%28Onboarding%20%2B%20Networking%29.md),
loadable into Neo4j, plus `manifest.json` for corpus coherence (TASK-002).

## Quick start

```bash
cd on-prem/datagen
pip install -r requirements.txt

# Fast offline run (no Ollama required)
python generate.py --no-llm

# Full run with Ollama narrative generation
# (requires Ollama running at localhost:11434 with llama3.3 pulled)
python generate.py

# Custom seed + output directory
python generate.py --seed 99 --output-dir /tmp/org --no-llm
```

## Options

| Flag | Default | Description |
|---|---|---|
| `--num-people` | 400 | Total headcount (includes new hires) |
| `--num-new-hires` | 30 | New-hire cohort size (1–2 cohorts) |
| `--num-engagements` | 20 | Client engagements to generate |
| `--seed` | 42 | Random seed — same seed → identical output |
| `--output-dir` | `output/` | Where to write CSVs, `load.cypher`, `manifest.json` |
| `--ollama-model` | `llama3.3` | Ollama model for ERG names, client names, bios |
| `--no-llm` | false | Skip Ollama; use templated values (fast, offline) |

## Output

```
output/
├── nodes_Person.csv          # ~400 rows
├── nodes_Role.csv
├── nodes_Team.csv
├── nodes_Practice.csv
├── nodes_Location.csv
├── nodes_Engagement.csv
├── nodes_Community.csv       # ERGs + communities of practice + interest groups
├── nodes_Journey.csv         # one per practice
├── nodes_Stage.csv           # 6 stages per journey
├── nodes_Task.csv            # task templates (shared per stage)
├── nodes_Milestone.csv
├── nodes_Skill.csv
├── nodes_Interest.csv
├── nodes_PulseResponse.csv
├── rels_reports_to.csv       # org hierarchy DAG
├── rels_member_of.csv        # Person → Team
├── rels_part_of.csv          # Team → Practice
├── rels_has_role.csv
├── rels_based_at.csv
├── rels_staffed_on.csv       # Person → Engagement
├── rels_leads_team.csv
├── rels_leads_practice.csv
├── rels_leads_engagement.csv
├── rels_buddy_of.csv
├── rels_mentor_of.csv
├── rels_cohort_with.csv      # symmetric — both directions stored
├── rels_member_of_community.csv
├── rels_expert_in.csv
├── rels_ask_me_about.csv
├── rels_interested_in.csv
├── rels_assigned_journey.csv
├── rels_has_stage.csv
├── rels_includes_task.csv
├── rels_responsible_for.csv  # Task → Person, with new_hire_id property
├── rels_completed.csv        # Person → Task, with status + timestamp
├── rels_reaches.csv          # Person → Milestone
├── rels_responded.csv        # Person → PulseResponse
├── rels_collaborates_with.csv# derived from shared team/engagement; is_derived=True
├── load.cypher               # LOAD CSV script for Neo4j
└── manifest.json             # coherence bridge for TASK-002 corpus generator
```

## Loading into Neo4j

1. Copy all `*.csv` files from `output/` into Neo4j's import directory:
   - Docker Compose: `docker cp output/. mentorforge-neo4j-1:/var/lib/neo4j/import/`
   - Local install: copy to `$NEO4J_HOME/import/`

2. Run the load script:
   ```bash
   cypher-shell -u neo4j -p <password> -f output/load.cypher
   ```
   Or paste `load.cypher` into Neo4j Browser.

3. Verify:
   ```cypher
   MATCH (n:Person) RETURN count(n);           // ~400
   MATCH (p:Person {status:'onboarding'}) RETURN p.name, p.start_date LIMIT 5;
   MATCH (nh:Person {status:'onboarding'})-[:BUDDY_OF]->(b) RETURN nh.name, b.name LIMIT 5;
   ```

## Design notes

- **Shared journey templates:** one `Journey` per practice with 6 shared `Stage` and
  `Task` nodes. `RESPONSIBLE_FOR` carries `new_hire_id` to bind each task to its
  specific owner (manager/buddy/HR) per new hire. `COMPLETED` is per-person.
- **`collaborates_with` is derived:** materialized from shared team + engagement
  membership; marked `is_derived=True`. At query time the agent can also derive it
  fresh — stored here for demo performance.
- **`should_meet` and `recommended_for` not generated** — query-time inferences per
  the schema spec.
- **Consent attrs:** `discoverable` and `networking_opt_in` are set on every `Person`;
  ~15% opted out of discoverability, ~20% opted out of networking, so the demo can
  show opt-out being respected.
- **`manifest.json`** is the coherence bridge to TASK-002: it lists all named
  people/teams/practices/engagements/ERGs so the corpus generator can reference the
  same entity names.
