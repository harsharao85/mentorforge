#!/usr/bin/env python3
"""
patch_cast.py — Inject demo cast names into TASK-001 output.

Reads datagen/output/ CSVs + manifest.json, patches specific persons and
engagements to match the 3 EX Stories demo script, writes everything back.

Cast injected:
  New hires:
    Priya Nair      → Data practice, Vancouver, Senior Consultant, onboarding
    Marcus Lee      → Cloud practice, Toronto, Consultant, onboarding
    Aisha Rahman    → Strategy practice, London, Analyst, onboarding

  Existing staff:
    Sarah Chen      → Data practice lead (Partner/Director who leads practice-data)
    Ben Okonkwo     → Priya's reports_to manager
    Tom Rivera      → Priya's buddy_of buddy
    Lena Hofer      → Atlas-Health engagement lead
    Dana Okafor     → Cloud practice, expert_in Unity Catalog
    Jordan Chen     → Cloud practice, networking_opt_in=False (Story 2 consent demo)
    Sam Park        → Helios engagement (any staffed person)
    Raj Mehta       → Helios engagement (second staffed person)

Engagements:
    First healthcare engagement  → Atlas-Health (HIPAA-regulated)
    First retail engagement      → Northwind
    Any active engagement        → Meridian (Unity Catalog retro)
    Another active engagement    → Helios

Also:
  - Adds skill-unity-catalog to nodes_Skill.csv
  - Adds expert_in(Dana, unity-catalog) to rels_expert_in.csv
  - Updates email domain @meridian-consulting.demo → @northstar-consulting.demo
  - Rewrites manifest.json
"""

import csv
import json
import sys
from pathlib import Path

DATAGEN_OUTPUT = Path(__file__).parent.parent / "datagen" / "output"


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] = None):
    if not rows:
        return
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    out = DATAGEN_OUTPUT
    if not (out / "manifest.json").exists():
        sys.exit(f"TASK-001 output not found at {out}. Run generate.py first.")

    print(f"Loading TASK-001 output from {out}/...")

    # ── Load ─────────────────────────────────────────────────────────────────
    persons        = load_csv(out / "nodes_Person.csv")
    engagements    = load_csv(out / "nodes_Engagement.csv")
    skills         = load_csv(out / "nodes_Skill.csv")
    reports_to     = load_csv(out / "rels_reports_to.csv")
    buddy_of       = load_csv(out / "rels_buddy_of.csv")
    leads_practice = load_csv(out / "rels_leads_practice.csv")
    leads_engmt    = load_csv(out / "rels_leads_engagement.csv")
    staffed_on     = load_csv(out / "rels_staffed_on.csv")
    expert_in      = load_csv(out / "rels_expert_in.csv")
    manifest       = json.loads((out / "manifest.json").read_text())

    # Index helpers
    person_by_id  = {p["id"]: p for p in persons}
    engmt_by_id   = {e["id"]: e for e in engagements}

    # ── Step 1: Rename engagements ────────────────────────────────────────────
    print("  Patching engagements...")

    # Atlas-Health: first healthcare engagement
    healthcare = [e for e in engagements if "health" in e["industry"].lower()]
    if not healthcare:
        healthcare = [e for e in engagements if e["status"] == "active"]
    atlas_id = healthcare[0]["id"]
    engmt_by_id[atlas_id]["client"] = "Atlas-Health"
    engmt_by_id[atlas_id]["industry"] = "Healthcare"
    engmt_by_id[atlas_id]["status"] = "active"

    # Northwind: first retail/CPG engagement (different from Atlas)
    retail = [e for e in engagements
              if ("retail" in e["industry"].lower() or "cpg" in e["industry"].lower())
              and e["id"] != atlas_id]
    if not retail:
        retail = [e for e in engagements if e["id"] != atlas_id and e["status"] == "active"]
    northwind_id = retail[0]["id"]
    engmt_by_id[northwind_id]["client"] = "Northwind"
    engmt_by_id[northwind_id]["industry"] = "Retail & CPG"
    engmt_by_id[northwind_id]["status"] = "active"

    # Meridian: active, different from above
    meridian_candidates = [e for e in engagements
                           if e["id"] not in (atlas_id, northwind_id)
                           and e["status"] == "active"]
    meridian_id = meridian_candidates[0]["id"]
    engmt_by_id[meridian_id]["client"] = "Meridian"
    engmt_by_id[meridian_id]["status"] = "active"

    # Helios: active, different from all above
    helios_candidates = [e for e in engagements
                         if e["id"] not in (atlas_id, northwind_id, meridian_id)
                         and e["status"] == "active"]
    if helios_candidates:
        helios_id = helios_candidates[0]["id"]
        engmt_by_id[helios_id]["client"] = "Helios"
        engmt_by_id[helios_id]["status"] = "active"
    else:
        helios_id = None

    # ── Step 2: Find and patch key existing staff ─────────────────────────────
    print("  Patching existing staff cast...")

    # Sarah Chen → Data practice lead (leads practice-data)
    data_practice_leaders = {e["from_id"] for e in leads_practice if e["to_id"] == "practice-data"}
    # Pick a partner or director in data practice
    sarah_candidates = [p for p in persons
                        if p["id"] in data_practice_leaders
                        and p["level"] in ("Partner", "Director", "Managing Partner")]
    if not sarah_candidates:
        sarah_candidates = [p for p in persons if p["id"] in data_practice_leaders]
    if sarah_candidates:
        sarah = sarah_candidates[0]
        sarah["name"] = "Sarah Chen"
        sarah["email"] = "sarah-chen-" + sarah["id"][-4:] + "@northstar-consulting.com"

    # Find the Data practice new hires first (for Priya)
    data_new_hires = [p for p in persons
                      if p["status"] == "onboarding"
                      and any(e["from_id"] == p["id"]
                              for e in load_csv(out / "rels_member_of.csv"))]
    # Actually filter by practice via member_of → team → part_of
    member_of     = load_csv(out / "rels_member_of.csv")
    teams         = load_csv(out / "nodes_Team.csv")
    team_practice = {t["id"]: t["practice_id"] for t in teams}
    person_practice = {}
    for edge in member_of:
        pid = edge["from_id"]
        tid = edge["to_id"]
        if tid in team_practice:
            person_practice[pid] = team_practice[tid]

    # Fall back: internal _practice_id isn't in CSV nodes, use manifest
    nh_map = {nh["id"]: nh for nh in manifest["new_hires"]}

    def nh_by_practice(practice_id):
        return [p for p in persons
                if p["status"] == "onboarding"
                and nh_map.get(p["id"], {}).get("practice_id") == practice_id]

    def active_by_practice(practice_id, levels=None):
        result = []
        for p in persons:
            if p["status"] != "active":
                continue
            if person_practice.get(p["id"]) != practice_id:
                continue
            if levels and p["level"] not in levels:
                continue
            result.append(p)
        return result

    # ── Step 3: Patch new hires ───────────────────────────────────────────────
    print("  Patching new hire cast...")

    # Priya Nair — Data practice, onboarding, Senior Consultant, Vancouver
    priya_candidates = nh_by_practice("practice-data")
    if not priya_candidates:
        priya_candidates = [p for p in persons if p["status"] == "onboarding"][:1]
    priya = priya_candidates[0]
    priya_id = priya["id"]
    priya["name"] = "Priya Nair"
    priya["email"] = "priya-nair-" + priya_id[-4:] + "@northstar-consulting.com"
    priya["level"] = "Senior Consultant"
    priya["ladder_level"] = "Senior Consultant"
    priya["location_id"] = "loc-van"
    priya["timezone"] = "America/Vancouver"

    # Marcus Lee — Cloud practice, onboarding, Consultant, Toronto
    marcus_candidates = [p for p in nh_by_practice("practice-cloud") if p["id"] != priya_id]
    if not marcus_candidates:
        marcus_candidates = [p for p in persons if p["status"] == "onboarding" and p["id"] != priya_id][:1]
    marcus = marcus_candidates[0]
    marcus_id = marcus["id"]
    marcus["name"] = "Marcus Lee"
    marcus["email"] = "marcus-lee-" + marcus_id[-4:] + "@northstar-consulting.com"
    marcus["level"] = "Consultant"
    marcus["ladder_level"] = "Consultant"
    marcus["location_id"] = "loc-tor"
    marcus["timezone"] = "America/Toronto"

    # Aisha Rahman — Strategy practice, onboarding, Analyst, London
    aisha_candidates = [p for p in nh_by_practice("practice-strategy")
                        if p["id"] not in (priya_id, marcus_id)]
    if not aisha_candidates:
        aisha_candidates = [p for p in persons
                            if p["status"] == "onboarding"
                            and p["id"] not in (priya_id, marcus_id)][:1]
    aisha = aisha_candidates[0]
    aisha_id = aisha["id"]
    aisha["name"] = "Aisha Rahman"
    aisha["email"] = "aisha-rahman-" + aisha_id[-4:] + "@northstar-consulting.com"
    aisha["level"] = "Analyst"
    aisha["ladder_level"] = "Analyst"
    aisha["location_id"] = "loc-lon"
    aisha["timezone"] = "Europe/London"

    # Ben Okonkwo — Priya's manager
    priya_manager_id = next((e["to_id"] for e in reports_to if e["from_id"] == priya_id), None)
    if priya_manager_id and priya_manager_id in person_by_id:
        ben = person_by_id[priya_manager_id]
        ben["name"] = "Ben Okonkwo"
        ben["email"] = "ben-okonkwo-" + ben["id"][-4:] + "@northstar-consulting.com"

    # Tom Rivera — Priya's buddy
    priya_buddy_id = next((e["to_id"] for e in buddy_of if e["from_id"] == priya_id), None)
    if priya_buddy_id and priya_buddy_id in person_by_id:
        tom = person_by_id[priya_buddy_id]
        tom["name"] = "Tom Rivera"
        tom["email"] = "tom-rivera-" + tom["id"][-4:] + "@northstar-consulting.com"

    # Lena Hofer — Atlas-Health engagement lead
    atlas_lead_ids = {e["from_id"] for e in leads_engmt if e["to_id"] == atlas_id}
    for lid in atlas_lead_ids:
        if lid in person_by_id:
            p = person_by_id[lid]
            p["name"] = "Lena Hofer"
            p["email"] = "lena-hofer-" + p["id"][-4:] + "@northstar-consulting.com"
            break

    # Dana Okafor — Cloud practice, active, expert_in Unity Catalog
    cloud_active = active_by_practice("practice-cloud",
                                      levels=["Senior Consultant", "Manager", "Director"])
    # Exclude already-named people
    named_ids = {priya_id, marcus_id, aisha_id}
    if priya_manager_id:
        named_ids.add(priya_manager_id)
    dana_candidates = [p for p in cloud_active if p["id"] not in named_ids]
    dana = dana_candidates[0] if dana_candidates else cloud_active[0]
    dana["name"] = "Dana Okafor"
    dana["email"] = "dana-okafor-" + dana["id"][-4:] + "@northstar-consulting.com"
    dana["discoverable"] = True
    dana["networking_opt_in"] = True
    dana_id = dana["id"]

    # Jordan Chen — Cloud practice, networking_opt_in=False (Story 2 consent demo)
    jordan_candidates = [p for p in cloud_active
                         if p["id"] not in named_ids | {dana_id}]
    if jordan_candidates:
        jordan = jordan_candidates[0]
        jordan["name"] = "Jordan Chen"
        jordan["email"] = "jordan-chen-" + jordan["id"][-4:] + "@northstar-consulting.com"
        jordan["networking_opt_in"] = False
        jordan["discoverable"] = False

    # Sam Park + Raj Mehta — staffed on Helios
    if helios_id:
        helios_staffed = [e["from_id"] for e in staffed_on if e["to_id"] == helios_id]
        helios_staffed = [pid for pid in helios_staffed if pid not in named_ids]
        if len(helios_staffed) >= 1:
            p = person_by_id[helios_staffed[0]]
            p["name"] = "Sam Park"
            p["email"] = "sam-park-" + p["id"][-4:] + "@northstar-consulting.com"
        if len(helios_staffed) >= 2:
            p = person_by_id[helios_staffed[1]]
            p["name"] = "Raj Mehta"
            p["email"] = "raj-mehta-" + p["id"][-4:] + "@northstar-consulting.com"

    # ── Step 4: Add Unity Catalog skill + edge ────────────────────────────────
    print("  Adding skill-unity-catalog + Dana expert_in edge...")

    if not any(s["id"] == "skill-unity-catalog" for s in skills):
        skills.append({"id": "skill-unity-catalog", "name": "Databricks Unity Catalog", "category": "Data"})

    # Add expert_in and ask_me_about edges for Dana
    if not any(e["from_id"] == dana_id and e["to_id"] == "skill-unity-catalog" for e in expert_in):
        expert_in.append({"from_id": dana_id, "to_id": "skill-unity-catalog"})

    ask_me_about = load_csv(out / "rels_ask_me_about.csv")
    if not any(e["from_id"] == dana_id and e["to_id"] == "skill-unity-catalog" for e in ask_me_about):
        ask_me_about.append({"from_id": dana_id, "to_id": "skill-unity-catalog"})

    # ── Step 5: Update email domain for all remaining persons ─────────────────
    print("  Updating email domain @meridian-consulting.demo → @northstar-consulting.com...")
    for p in persons:
        if "@meridian-consulting.demo" in p.get("email", ""):
            p["email"] = p["email"].replace("@meridian-consulting.demo", "@northstar-consulting.com")

    # ── Step 6: Write CSV files ───────────────────────────────────────────────
    print("  Writing patched CSVs...")

    write_csv(out / "nodes_Person.csv", persons, list(persons[0].keys()))
    write_csv(out / "nodes_Engagement.csv", list(engmt_by_id.values()), list(engagements[0].keys()))
    write_csv(out / "nodes_Skill.csv", skills, ["id", "name", "category"])
    write_csv(out / "rels_expert_in.csv", expert_in, ["from_id", "to_id"])
    write_csv(out / "rels_ask_me_about.csv", ask_me_about, ["from_id", "to_id"])

    # ── Step 7: Update manifest.json ─────────────────────────────────────────
    print("  Updating manifest.json...")

    pid_to_name = {p["id"]: p["name"] for p in persons}
    pid_to_email = {p["id"]: p["email"] for p in persons}
    eid_to_client = {e["id"]: e["client"] for e in engmt_by_id.values()}

    # Update manifest new_hires
    for nh in manifest["new_hires"]:
        if nh["id"] in pid_to_name:
            nh["name"] = pid_to_name[nh["id"]]
            nh["email"] = pid_to_email[nh["id"]]

    # Update manifest people
    for p in manifest["people"]:
        if p["id"] in pid_to_name:
            p["name"] = pid_to_name[p["id"]]
            p["email"] = pid_to_email[p["id"]]

    # Update manifest engagements
    for e in manifest["engagements"]:
        if e["id"] in eid_to_client:
            e["client"] = eid_to_client[e["id"]]

    # Add cast index to manifest for corpus generator
    manifest["demo_cast"] = {
        "company": "Northstar Consulting",
        "new_hires": {
            "priya": {"id": priya_id, "name": "Priya Nair",
                      "practice": "Data", "location": "Vancouver", "level": "Senior Consultant"},
            "marcus": {"id": marcus_id, "name": "Marcus Lee",
                       "practice": "Cloud", "location": "Toronto", "level": "Consultant"},
            "aisha": {"id": aisha_id, "name": "Aisha Rahman",
                      "practice": "Strategy", "location": "London", "level": "Analyst"},
        },
        "staff": {
            "sarah": {"id": (sarah_candidates[0]["id"] if sarah_candidates else ""), "name": "Sarah Chen",
                      "role": "Data Practice Lead"},
            "ben": {"id": priya_manager_id or "", "name": "Ben Okonkwo",
                    "role": "Data Manager, Priya's manager"},
            "tom": {"id": priya_buddy_id or "", "name": "Tom Rivera",
                    "role": "Senior Consultant, Priya's buddy"},
            "lena": {"id": list(atlas_lead_ids)[0] if atlas_lead_ids else "", "name": "Lena Hofer",
                     "role": "Atlas-Health engagement lead"},
            "dana": {"id": dana_id, "name": "Dana Okafor",
                     "role": "Cloud Senior Consultant, Unity Catalog expert"},
        },
        "engagements": {
            "atlas_health": atlas_id,
            "northwind": northwind_id,
            "meridian": meridian_id,
            "helios": helios_id,
        },
    }

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # Summary
    print("\nCast injected:")
    print(f"  Priya Nair     → {priya_id} (Data/Vancouver)")
    print(f"  Marcus Lee     → {marcus_id} (Cloud/Toronto)")
    print(f"  Aisha Rahman   → {aisha_id} (Strategy/London)")
    print(f"  Ben Okonkwo    → {priya_manager_id} (Priya's manager)")
    print(f"  Tom Rivera     → {priya_buddy_id} (Priya's buddy)")
    print(f"  Dana Okafor    → {dana_id} (Cloud, Unity Catalog)")
    print(f"\nEngagements renamed:")
    print(f"  Atlas-Health   → {atlas_id}")
    print(f"  Northwind      → {northwind_id}")
    print(f"  Meridian       → {meridian_id}")
    print(f"  Helios         → {helios_id}")
    print("\nDone. Re-run load.cypher to reload Neo4j with the patched data.")


if __name__ == "__main__":
    main()
