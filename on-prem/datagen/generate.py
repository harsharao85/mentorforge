#!/usr/bin/env python3
"""
MentorForge — Synthetic org/people graph generator.

Produces a synthetic IT-services/management-consulting org matching
Graph Schema v2, loadable into Neo4j, plus manifest.json for corpus
coherence (TASK-002).

Usage:
    python generate.py [--no-llm] [--seed 42] [--output-dir output/]
    python generate.py --help
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

try:
    from faker import Faker
except ImportError:
    sys.exit("Missing dependency. Run: pip install -r requirements.txt")

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


# ---------------------------------------------------------------------------
# Static catalogs
# ---------------------------------------------------------------------------

PRACTICES = [
    {"id": "practice-cloud",    "name": "Cloud"},
    {"id": "practice-data",     "name": "Data"},
    {"id": "practice-cyber",    "name": "Cyber"},
    {"id": "practice-strategy", "name": "Strategy"},
    {"id": "practice-appdev",   "name": "App Dev"},
]

PRACTICE_TEAMS = {
    "practice-cloud":    ["Cloud Infrastructure", "Cloud Architecture", "Cloud Migration", "FinOps & Governance"],
    "practice-data":     ["Data Engineering", "Analytics & BI", "ML & AI", "Data Governance"],
    "practice-cyber":    ["Security Operations", "Identity & Access", "GRC & Compliance", "Red Team"],
    "practice-strategy": ["Digital Strategy", "Org Transformation", "PMO & Delivery", "M&A Advisory"],
    "practice-appdev":   ["Full-Stack Engineering", "Platform Engineering", "Mobile & UX", "DevSecOps"],
}

# Skills scoped by practice for realistic expert_in assignment
PRACTICE_SKILLS = {
    "practice-cloud":    ["skill-aws", "skill-azure", "skill-gcp", "skill-k8s", "skill-terraform"],
    "practice-data":     ["skill-spark", "skill-dbt", "skill-databricks", "skill-sql", "skill-python"],
    "practice-cyber":    ["skill-soc", "skill-iam", "skill-devsecops", "skill-pentest"],
    "practice-strategy": ["skill-change", "skill-ops-model", "skill-ma", "skill-roadmap", "skill-proposal"],
    "practice-appdev":   ["skill-react", "skill-typescript", "skill-java", "skill-cicd", "skill-python"],
}

SKILLS_CATALOG = [
    {"id": "skill-aws",        "name": "Amazon Web Services",    "category": "Cloud"},
    {"id": "skill-azure",      "name": "Microsoft Azure",        "category": "Cloud"},
    {"id": "skill-gcp",        "name": "Google Cloud Platform",  "category": "Cloud"},
    {"id": "skill-k8s",        "name": "Kubernetes",             "category": "Cloud"},
    {"id": "skill-terraform",  "name": "Terraform",              "category": "Cloud"},
    {"id": "skill-spark",      "name": "Apache Spark",           "category": "Data"},
    {"id": "skill-dbt",        "name": "dbt",                    "category": "Data"},
    {"id": "skill-databricks", "name": "Databricks",             "category": "Data"},
    {"id": "skill-sql",        "name": "SQL & Data Modeling",    "category": "Data"},
    {"id": "skill-python",     "name": "Python",                 "category": "Data"},
    {"id": "skill-mlops",      "name": "MLOps",                  "category": "AI/ML"},
    {"id": "skill-genai",      "name": "Generative AI",          "category": "AI/ML"},
    {"id": "skill-bedrock",    "name": "Amazon Bedrock",         "category": "AI/ML"},
    {"id": "skill-llmops",     "name": "LLMOps",                 "category": "AI/ML"},
    {"id": "skill-soc",        "name": "SOC Operations",         "category": "Cyber"},
    {"id": "skill-iam",        "name": "Identity & Access Mgmt", "category": "Cyber"},
    {"id": "skill-devsecops",  "name": "DevSecOps",              "category": "Cyber"},
    {"id": "skill-pentest",    "name": "Penetration Testing",    "category": "Cyber"},
    {"id": "skill-change",     "name": "Change Management",      "category": "Strategy"},
    {"id": "skill-ops-model",  "name": "Operating Model Design", "category": "Strategy"},
    {"id": "skill-ma",         "name": "M&A Due Diligence",      "category": "Strategy"},
    {"id": "skill-roadmap",    "name": "Technology Roadmapping", "category": "Strategy"},
    {"id": "skill-proposal",   "name": "Proposal Writing",       "category": "Leadership"},
    {"id": "skill-delivery",   "name": "Delivery Management",    "category": "Leadership"},
    {"id": "skill-account",    "name": "Account Management",     "category": "Leadership"},
    {"id": "skill-workshop",   "name": "Workshop Facilitation",  "category": "Leadership"},
    {"id": "skill-react",      "name": "React",                  "category": "App Dev"},
    {"id": "skill-typescript", "name": "TypeScript",             "category": "App Dev"},
    {"id": "skill-java",       "name": "Java",                   "category": "App Dev"},
    {"id": "skill-cicd",       "name": "CI/CD Pipelines",        "category": "App Dev"},
]

INTERESTS_CATALOG = [
    {"id": "int-hiking",          "name": "Hiking & Outdoors"},
    {"id": "int-cycling",         "name": "Cycling"},
    {"id": "int-photography",     "name": "Photography"},
    {"id": "int-cooking",         "name": "Cooking"},
    {"id": "int-travel",          "name": "Travel"},
    {"id": "int-gaming",          "name": "Gaming"},
    {"id": "int-music",           "name": "Music"},
    {"id": "int-running",         "name": "Running"},
    {"id": "int-yoga",            "name": "Yoga & Meditation"},
    {"id": "int-startups",        "name": "Startups & Entrepreneurship"},
    {"id": "int-investing",       "name": "Investing & Finance"},
    {"id": "int-scitech",         "name": "Science & Technology"},
    {"id": "int-volunteering",    "name": "Volunteering"},
    {"id": "int-writing",         "name": "Writing & Blogging"},
    {"id": "int-reading",         "name": "Reading"},
    {"id": "int-sports",          "name": "Team Sports"},
    {"id": "int-parenting",       "name": "Parenting"},
    {"id": "int-craft",           "name": "Crafts & DIY"},
    {"id": "int-podcast",         "name": "Podcasting"},
    {"id": "int-sustainability",  "name": "Sustainability"},
]

DEFAULT_COMMUNITIES = [
    {"type": "ERG",                   "name": "Women in Tech",          "blurb": "Supporting and advancing women across all career stages."},
    {"type": "ERG",                   "name": "LGBTQ+ Alliance",        "blurb": "Championing inclusion and visibility for LGBTQ+ employees."},
    {"type": "ERG",                   "name": "Cultural Mosaic",        "blurb": "Celebrating the richness of our global cultural backgrounds."},
    {"type": "ERG",                   "name": "Early Career Network",   "blurb": "Helping analysts and consultants build the foundations they need."},
    {"type": "ERG",                   "name": "Parents & Caregivers",   "blurb": "Peer support and resources for working parents and caregivers."},
    {"type": "community_of_practice", "name": "Cloud Guild",            "blurb": "Deep dives into cloud architecture, patterns, and vendor news."},
    {"type": "community_of_practice", "name": "Data Science Community", "blurb": "Cross-practice learning on ML, analytics, and data engineering."},
    {"type": "community_of_practice", "name": "Security Community",     "blurb": "Threat intel sharing, CTF nights, and security career development."},
    {"type": "community_of_practice", "name": "AI/GenAI Guild",         "blurb": "Exploring generative AI use cases, LLMOps, and responsible AI."},
    {"type": "interest_group",        "name": "Outdoor Adventure",      "blurb": "Hiking, skiing, kayaking — any excuse to get outside together."},
    {"type": "interest_group",        "name": "Foodies & Home Chefs",   "blurb": "Recipe swaps, lunch spots, and the annual chili cook-off."},
    {"type": "interest_group",        "name": "Investors & Markets",    "blurb": "Market watchers, FIRE enthusiasts, and the occasional options trader."},
]

LOCATIONS = [
    {"id": "loc-van", "office": "Vancouver",  "geo": "North America", "timezone": "America/Vancouver"},
    {"id": "loc-tor", "office": "Toronto",    "geo": "North America", "timezone": "America/Toronto"},
    {"id": "loc-nyc", "office": "New York",   "geo": "North America", "timezone": "America/New_York"},
    {"id": "loc-lon", "office": "London",     "geo": "EMEA",          "timezone": "Europe/London"},
    {"id": "loc-sgp", "office": "Singapore",  "geo": "APAC",          "timezone": "Asia/Singapore"},
    {"id": "loc-syd", "office": "Sydney",     "geo": "APAC",          "timezone": "Australia/Sydney"},
    {"id": "loc-fra", "office": "Frankfurt",  "geo": "EMEA",          "timezone": "Europe/Berlin"},
    {"id": "loc-dub", "office": "Dubai",      "geo": "EMEA",          "timezone": "Asia/Dubai"},
]

LADDER_LEVELS = [
    "Analyst", "Consultant", "Senior Consultant",
    "Manager", "Senior Manager", "Director",
    "Partner", "Managing Partner",
]

ROLE_FAMILIES = {
    "Analyst": "Delivery", "Consultant": "Delivery",
    "Senior Consultant": "Delivery", "Manager": "Delivery",
    "Senior Manager": "Leadership", "Director": "Leadership",
    "Partner": "Leadership", "Managing Partner": "Leadership",
}

# Pyramid: fraction of active (non-new-hire) headcount per level
PYRAMID_WEIGHTS = {
    "Managing Partner": 1,
    "Partner": 5,
    "Director": 10,
    "Senior Manager": 20,
    "Manager": 40,
    "Senior Consultant": 80,
    "Consultant": 110,
    "Analyst": 104,
}

INDUSTRIES = [
    "Financial Services", "Healthcare", "Retail & CPG", "Energy & Utilities",
    "Government & Public Sector", "Telecommunications", "Manufacturing",
    "Insurance", "Media & Entertainment", "Life Sciences",
    "Transportation & Logistics",
]

# Stage offset window: (days_from_start_inclusive, days_from_start_inclusive)
# preboard uses negative offsets (before day 0)
STAGE_WINDOWS = {
    "preboard": (-14, -1),
    "day_1":    (0,   1),
    "week_1":   (2,   7),
    "day_30":   (8,   30),
    "day_60":   (31,  60),
    "day_90":   (61,  90),
}

# Shared task templates keyed by stage name.
# owner_role: new_hire | manager | buddy | HR | IT
TASK_TEMPLATES = {
    "preboard": [
        {"title": "Sign offer letter via DocuSign",                  "category": "admin",      "owner_role": "new_hire", "due_offset": -14, "mandatory": True},
        {"title": "Submit ID documents for background check",         "category": "compliance", "owner_role": "HR",       "due_offset": -10, "mandatory": True},
        {"title": "Complete pre-boarding survey",                     "category": "cultural",   "owner_role": "new_hire", "due_offset": -7,  "mandatory": False},
        {"title": "Set up laptop shipment and home office stipend",   "category": "admin",      "owner_role": "IT",       "due_offset": -7,  "mandatory": True},
        {"title": "Connect with your buddy before day one",          "category": "social",     "owner_role": "buddy",    "due_offset": -3,  "mandatory": False},
    ],
    "day_1": [
        {"title": "Collect laptop and access badge",                  "category": "admin",      "owner_role": "IT",       "due_offset": 0,   "mandatory": True},
        {"title": "Attend new-hire orientation",                      "category": "cultural",   "owner_role": "HR",       "due_offset": 0,   "mandatory": True},
        {"title": "1:1 intro with your manager",                      "category": "social",     "owner_role": "manager",  "due_offset": 0,   "mandatory": True},
        {"title": "1:1 coffee with your buddy",                       "category": "social",     "owner_role": "buddy",    "due_offset": 1,   "mandatory": True},
        {"title": "Join team Slack channels and email groups",        "category": "admin",      "owner_role": "new_hire", "due_offset": 0,   "mandatory": True},
    ],
    "week_1": [
        {"title": "Complete security awareness training",             "category": "compliance", "owner_role": "new_hire", "due_offset": 5,   "mandatory": True},
        {"title": "Read the practice capability deck",                "category": "role",       "owner_role": "new_hire", "due_offset": 5,   "mandatory": True},
        {"title": "Meet all members of your immediate team",          "category": "social",     "owner_role": "manager",  "due_offset": 5,   "mandatory": False},
        {"title": "Set up billing profile and expenses account",      "category": "admin",      "owner_role": "HR",       "due_offset": 3,   "mandatory": True},
        {"title": "Shadow a client call or delivery session",         "category": "role",       "owner_role": "manager",  "due_offset": 7,   "mandatory": False},
    ],
    "day_30": [
        {"title": "Complete 30-day check-in with manager",            "category": "cultural",   "owner_role": "manager",  "due_offset": 30,  "mandatory": True},
        {"title": "Submit first timesheet and expense report",        "category": "admin",      "owner_role": "new_hire", "due_offset": 30,  "mandatory": True},
        {"title": "Join at least one ERG or community of practice",   "category": "social",     "owner_role": "new_hire", "due_offset": 30,  "mandatory": False},
        {"title": "Complete role-specific onboarding module",         "category": "role",       "owner_role": "new_hire", "due_offset": 30,  "mandatory": True},
    ],
    "day_60": [
        {"title": "60-day performance conversation with manager",     "category": "cultural",   "owner_role": "manager",  "due_offset": 60,  "mandatory": True},
        {"title": "Identify a stretch assignment or project",         "category": "role",       "owner_role": "manager",  "due_offset": 60,  "mandatory": False},
        {"title": "Complete benefits enrollment",                     "category": "admin",      "owner_role": "new_hire", "due_offset": 60,  "mandatory": True},
    ],
    "day_90": [
        {"title": "Complete 90-day review and set next-cycle goals",  "category": "cultural",   "owner_role": "manager",  "due_offset": 90,  "mandatory": True},
        {"title": "Deliver a short 'what I learned' to the team",     "category": "role",       "owner_role": "new_hire", "due_offset": 90,  "mandatory": False},
        {"title": "Nominate yourself for a community lead role",      "category": "social",     "owner_role": "new_hire", "due_offset": 90,  "mandatory": False},
    ],
}

MILESTONES = [
    {"id": "milestone-it-ready",   "name": "IT Ready",              "description": "Laptop set up, email active, VPN configured."},
    {"id": "milestone-first-call", "name": "First Client Touchpoint","description": "Participated in a client-facing session."},
    {"id": "milestone-30d-check",  "name": "30-Day Check-in Done",  "description": "30-day check-in completed with manager."},
    {"id": "milestone-community",  "name": "Community Connected",   "description": "Joined at least one ERG or community of practice."},
    {"id": "milestone-90d-review", "name": "90-Day Review Done",    "description": "Full onboarding cycle complete; goals set for next quarter."},
]

PULSE_COMMENTS = [
    "Great team, loving the onboarding so far.",
    "Buddy has been incredibly helpful this week.",
    "So much to learn but genuinely excited.",
    "Wish the IT setup had been smoother on day one.",
    "Best first two weeks at any company I have joined.",
    "The team orientation was very well run.",
    "Still finding my feet but everyone has been welcoming.",
]


# ---------------------------------------------------------------------------
# Ollama helper
# ---------------------------------------------------------------------------

def _ollama(prompt: str, model: str) -> Optional[str]:
    if not _HAS_REQUESTS:
        return None
    try:
        resp = _requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=90,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as exc:
        print(f"  [WARN] Ollama unavailable ({exc}) — using template fallback", file=sys.stderr)
        return None


def _parse_json_array(text: str) -> Optional[list]:
    try:
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end == -1:
            return None
        return json.loads(text[start:end + 1])
    except (json.JSONDecodeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class Generator:
    def __init__(self, args):
        self.args = args
        import random
        self.rng = random.Random(args.seed)
        self.fake = Faker()
        self.fake.seed_instance(args.seed)
        Faker.seed(args.seed)

        self._pid_counter = 0
        self._active_persons = []   # active staff
        self._new_hire_list = []    # new hires
        self._persons_by_level = {level: [] for level in LADDER_LEVELS}

        # Nodes
        self.n_persons = []
        self.n_roles = []
        self.n_teams = []
        self.n_practices = list(PRACTICES)
        self.n_locations = list(LOCATIONS)
        self.n_engagements = []
        self.n_communities = []
        self.n_skills = list(SKILLS_CATALOG)
        self.n_interests = list(INTERESTS_CATALOG)
        self.n_journeys = []
        self.n_stages = []
        self.n_tasks = []
        self.n_milestones = list(MILESTONES)
        self.n_pulse = []

        # Edges
        self.e_reports_to = []
        self.e_member_of = []
        self.e_part_of = []
        self.e_has_role = []
        self.e_based_at = []
        self.e_staffed_on = []
        self.e_leads_team = []
        self.e_leads_practice = []
        self.e_leads_engagement = []
        self.e_buddy_of = []
        self.e_mentor_of = []
        self.e_cohort_with = []
        self.e_member_of_community = []
        self.e_expert_in = []
        self.e_ask_me_about = []
        self.e_interested_in = []
        self.e_assigned_journey = []
        self.e_has_stage = []
        self.e_includes_task = []
        self.e_responsible_for = []
        self.e_completed = []
        self.e_reaches = []
        self.e_responded = []
        self.e_collaborates_with = []

        # Lookup tables (built lazily)
        self._tasks_by_stage = {}       # stage_id → [task dict]
        self._stages_by_journey = {}    # journey_id → [stage dict]
        self._teams_by_practice = {}    # practice_id → [team dict]

    # -----------------------------------------------------------------------
    # Orchestrator
    # -----------------------------------------------------------------------

    def run(self):
        print("  reference data (practices, teams, locations, skills, ERGs)...")
        self._gen_reference()
        print("  org structure (persons, hierarchy, team assignment)...")
        self._gen_org()
        print("  social fabric (skills, interests, communities, mentors)...")
        self._gen_social()
        print("  journey templates (journeys, stages, tasks)...")
        self._gen_journey_templates()
        print("  new hires (cohorts, buddies, journey assignments)...")
        self._gen_new_hires()
        print("  engagements (clients, staffing)...")
        self._gen_engagements()
        print("  collaborates_with (derived, materialized from team+engagement)...")
        self._materialize_collaborates_with()

    # -----------------------------------------------------------------------
    # Reference data
    # -----------------------------------------------------------------------

    def _gen_reference(self):
        # Teams
        for practice_id, names in PRACTICE_TEAMS.items():
            for name in names:
                tid = f"team-{_slug(name)}"
                self.n_teams.append({"id": tid, "name": name, "function": name, "practice_id": practice_id})
                self.e_part_of.append({"from_id": tid, "to_id": practice_id})

        self._teams_by_practice = {}
        for team in self.n_teams:
            pid = team["practice_id"]
            self._teams_by_practice.setdefault(pid, []).append(team)

        # Communities (ERGs, CoPs, interest groups)
        self.n_communities = self._gen_communities()

    def _gen_communities(self):
        templates = list(DEFAULT_COMMUNITIES)
        if not self.args.no_llm:
            prompt = (
                "Generate 12 professional community/ERG names and one-sentence blurbs for a "
                "mid-size IT-services consulting firm. Mix: ERGs (diversity groups), "
                "communities of practice (technical), and interest groups (hobbies/social). "
                'Return ONLY a JSON array: [{"type":"ERG|community_of_practice|interest_group",'
                '"name":"...","blurb":"..."}]'
            )
            raw = _ollama(prompt, self.args.ollama_model)
            if raw:
                parsed = _parse_json_array(raw)
                if parsed:
                    templates = parsed[:12]

        result = []
        for i, t in enumerate(templates):
            result.append({
                "id": f"community-{i:03d}",
                "type": t.get("type", "interest_group"),
                "name": t.get("name", f"Community {i}"),
                "blurb": t.get("blurb", ""),
            })
        return result

    # -----------------------------------------------------------------------
    # Org structure
    # -----------------------------------------------------------------------

    def _next_pid(self) -> str:
        pid = f"person-{self._pid_counter:04d}"
        self._pid_counter += 1
        return pid

    def _make_person(self, level: str, practice_id: str = "", status: str = "active",
                     start_date: str = "", tenure_months: int = -1) -> dict:
        pid = self._next_pid()
        loc = self.rng.choice(self.n_locations)
        name = self.fake.name()
        email = f"{_slug(name)}-{pid[-4:]}@meridian-consulting.demo"

        if not start_date:
            offset = self.rng.randint(-1825, -90)   # 3 months–5 years ago
            start_date = (date.today() + timedelta(days=offset)).isoformat()
            tenure_months = abs(offset) // 30

        return {
            "id": pid,
            "name": name,
            "email": email,
            "status": status,
            "start_date": start_date,
            "level": level,
            "ladder_level": level,
            "location_id": loc["id"],
            "timezone": loc["timezone"],
            "languages": "en",
            "tenure_months": tenure_months,
            "employment_type": self.rng.choices(["full_time", "contractor"], weights=[90, 10])[0],
            "discoverable": self.rng.choices([True, False], weights=[85, 15])[0],
            "networking_opt_in": self.rng.choices([True, False], weights=[80, 20])[0],
            "work_style": self.rng.choice(["remote", "hybrid", "office"]),
            "bio": "",
            "_practice_id": practice_id,   # internal; not written to node CSV
        }

    def _gen_org(self):
        num_active = self.args.num_people - self.args.num_new_hires

        # Scale pyramid to target headcount
        base_total = sum(PYRAMID_WEIGHTS.values())
        scale = num_active / base_total
        counts = {}
        assigned = 0
        for level in LADDER_LEVELS[1:]:    # all except Analyst — Analyst absorbs the remainder
            n = max(1, round(PYRAMID_WEIGHTS[level] * scale))
            counts[level] = n
            assigned += n
        counts["Analyst"] = max(1, num_active - assigned)

        # One generic role per ladder level
        for level in LADDER_LEVELS:
            self.n_roles.append({
                "id": f"role-{_slug(level)}",
                "title": level,
                "role_family": ROLE_FAMILIES[level],
                "ladder_level": level,
            })

        practice_cycle = [p["id"] for p in self.n_practices]

        # Top-down hierarchy construction — guarantees DAG
        def add(level, practice_id, parent_id):
            p = self._make_person(level, practice_id=practice_id)
            self._persons_by_level[level].append(p)
            if parent_id:
                self.e_reports_to.append({"from_id": p["id"], "to_id": parent_id})
            return p

        # Managing Partner
        mp = add("Managing Partner", practice_cycle[0], "")
        self.e_leads_practice.append({"from_id": mp["id"], "to_id": practice_cycle[0]})

        # Partners — one per practice
        for practice in self.n_practices:
            p = add("Partner", practice["id"], mp["id"])
            self.e_leads_practice.append({"from_id": p["id"], "to_id": practice["id"]})

        # Directors, Senior Managers, Managers, Senior Consultants, Consultants, Analysts
        parent_map = {
            "Director":         "Partner",
            "Senior Manager":   "Director",
            "Manager":          "Senior Manager",
            "Senior Consultant":"Manager",
            "Consultant":       "Senior Consultant",
            "Analyst":          ("Consultant", "Senior Consultant"),
        }

        for level in ["Director", "Senior Manager", "Manager", "Senior Consultant", "Consultant", "Analyst"]:
            parent_level = parent_map[level]
            for i in range(counts.get(level, 0)):
                practice_id = practice_cycle[i % len(practice_cycle)]
                if isinstance(parent_level, tuple):
                    pool = []
                    for pl in parent_level:
                        pool.extend(self._persons_by_level[pl])
                else:
                    pool = self._persons_by_level[parent_level]
                parent = self.rng.choice(pool) if pool else mp
                add(level, practice_id, parent["id"])

        # Assign persons to teams
        all_active = []
        for level in LADDER_LEVELS:
            all_active.extend(self._persons_by_level[level])

        for person in all_active:
            pid = person["_practice_id"]
            teams = self._teams_by_practice.get(pid, [])
            if teams:
                team = self.rng.choice(teams)
                person["_team_id"] = team["id"]
                self.e_member_of.append({"from_id": person["id"], "to_id": team["id"]})
            else:
                person["_team_id"] = ""

        # Team leads: one Director per team where possible
        assigned_team_leads = set()
        for director in self._persons_by_level["Director"]:
            pid = director["_practice_id"]
            candidates = [t for t in self._teams_by_practice.get(pid, [])
                          if t["id"] not in assigned_team_leads]
            if candidates:
                team = self.rng.choice(candidates)
                assigned_team_leads.add(team["id"])
                self.e_leads_team.append({"from_id": director["id"], "to_id": team["id"]})

        # has_role and based_at
        for person in all_active:
            self.e_has_role.append({"from_id": person["id"], "to_id": f"role-{_slug(person['level'])}"})
            self.e_based_at.append({"from_id": person["id"], "to_id": person["location_id"]})

        self._active_persons = all_active
        self.n_persons.extend(all_active)

    # -----------------------------------------------------------------------
    # Social fabric (active staff only)
    # -----------------------------------------------------------------------

    def _gen_social(self):
        for person in self._active_persons:
            pid = person["_practice_id"]
            skill_pool = PRACTICE_SKILLS.get(pid, [s["id"] for s in self.n_skills])

            # expert_in (2–4 skills)
            chosen = self.rng.sample(skill_pool, min(self.rng.randint(2, 4), len(skill_pool)))
            for sid in chosen:
                self.e_expert_in.append({"from_id": person["id"], "to_id": sid})

            # ask_me_about (senior+ only, 1 skill from their expert set)
            if person["level"] in ("Senior Consultant", "Manager", "Senior Manager", "Director", "Partner", "Managing Partner"):
                if chosen:
                    self.e_ask_me_about.append({"from_id": person["id"], "to_id": self.rng.choice(chosen)})

            # interested_in (1–3)
            for interest in self.rng.sample(self.n_interests, self.rng.randint(1, 3)):
                self.e_interested_in.append({"from_id": person["id"], "to_id": interest["id"]})

            # member_of_community (1–3, only if discoverable)
            if person.get("discoverable"):
                for community in self.rng.sample(self.n_communities, self.rng.randint(1, 3)):
                    self.e_member_of_community.append({"from_id": person["id"], "to_id": community["id"]})

        # mentor_of: each Manager mentors 1 Consultant or Senior Consultant in same practice
        for manager in self._persons_by_level["Manager"]:
            mpid = manager["_practice_id"]
            candidates = [p for p in self._active_persons
                          if p["_practice_id"] == mpid
                          and p["level"] in ("Consultant", "Senior Consultant")]
            if candidates:
                mentee = self.rng.choice(candidates)
                self.e_mentor_of.append({"from_id": manager["id"], "to_id": mentee["id"]})

    # -----------------------------------------------------------------------
    # Journey templates (shared per practice)
    # -----------------------------------------------------------------------

    def _gen_journey_templates(self):
        for practice in self.n_practices:
            pslug = practice["id"].replace("practice-", "")
            jid = f"journey-{pslug}-new-hire"
            self.n_journeys.append({
                "id": jid,
                "type": "new_hire",
                "role_scope": "",
                "practice_scope": practice["id"],
            })
            self._stages_by_journey[jid] = []
            self._tasks_by_stage[jid] = {}

            for stage_name, (off_start, off_end) in STAGE_WINDOWS.items():
                sid = f"stage-{pslug}-{stage_name}"
                self.n_stages.append({
                    "id": sid,
                    "name": stage_name,
                    "journey_id": jid,
                    "offset_days_start": off_start,
                    "offset_days_end": off_end,
                })
                self.e_has_stage.append({"from_id": jid, "to_id": sid})
                self._stages_by_journey[jid].append({"id": sid, "name": stage_name})
                self._tasks_by_stage[sid] = []

                for i, tmpl in enumerate(TASK_TEMPLATES.get(stage_name, [])):
                    tid = f"task-{sid}-{i:02d}"
                    task = {
                        "id": tid,
                        "title": tmpl["title"],
                        "category": tmpl["category"],
                        "owner_role": tmpl["owner_role"],
                        "due_offset_days": tmpl["due_offset"],
                        "mandatory": tmpl["mandatory"],
                    }
                    self.n_tasks.append(task)
                    self.e_includes_task.append({"from_id": sid, "to_id": tid})
                    self._tasks_by_stage[sid].append(task)

    # -----------------------------------------------------------------------
    # New hires
    # -----------------------------------------------------------------------

    def _gen_new_hires(self):
        today = date.today()
        cohort_1_start = (today - timedelta(days=14)).isoformat()
        # Next Monday
        days_to_monday = (7 - today.weekday()) % 7 or 7
        cohort_2_start = (today + timedelta(days=days_to_monday)).isoformat()

        n1 = min(20, self.args.num_new_hires)
        n2 = self.args.num_new_hires - n1

        managers_pool = (self._persons_by_level["Manager"] +
                         self._persons_by_level["Senior Manager"])
        senior_pool = (self._persons_by_level["Senior Consultant"] +
                       self._persons_by_level["Consultant"])

        buddy_counts: dict[str, int] = {}
        practice_cycle = [p["id"] for p in self.n_practices]

        cohorts = [(n1, cohort_1_start, "onboarding"),
                   (n2, cohort_2_start, "pre_start")]

        cohort_groups = [[], []]   # cohort_groups[0] = cohort 1 new hire ids

        for cohort_idx, (count, start_date, status) in enumerate(cohorts):
            for i in range(count):
                practice_id = practice_cycle[i % len(practice_cycle)]
                nh = self._make_person(
                    level=self.rng.choice(["Analyst", "Consultant"]),
                    practice_id=practice_id,
                    status=status,
                    start_date=start_date,
                    tenure_months=0,
                )

                # Team
                teams = self._teams_by_practice.get(practice_id, [])
                if teams:
                    team = self.rng.choice(teams)
                    nh["_team_id"] = team["id"]
                    self.e_member_of.append({"from_id": nh["id"], "to_id": team["id"]})
                else:
                    nh["_team_id"] = ""

                # Manager (same practice preferred)
                pref_managers = [m for m in managers_pool
                                 if m["_practice_id"] == practice_id] or managers_pool
                manager = self.rng.choice(pref_managers)
                self.e_reports_to.append({"from_id": nh["id"], "to_id": manager["id"]})

                # Buddy (same practice, max 2 new hires per buddy)
                pref_seniors = [s for s in senior_pool
                                if s["_practice_id"] == practice_id] or senior_pool
                eligible = [s for s in pref_seniors if buddy_counts.get(s["id"], 0) < 2]
                if not eligible:
                    eligible = pref_seniors
                buddy = self.rng.choice(eligible)
                buddy_counts[buddy["id"]] = buddy_counts.get(buddy["id"], 0) + 1
                self.e_buddy_of.append({"from_id": nh["id"], "to_id": buddy["id"]})

                # has_role, based_at
                self.e_has_role.append({"from_id": nh["id"], "to_id": f"role-{_slug(nh['level'])}"})
                self.e_based_at.append({"from_id": nh["id"], "to_id": nh["location_id"]})

                # Journey assignment
                jid = f"journey-{practice_id.replace('practice-', '')}-new-hire"
                self.e_assigned_journey.append({"from_id": nh["id"], "to_id": jid})

                # responsible_for + completed per task
                days_in = 14 if status == "onboarding" else 0
                for stage in self._stages_by_journey.get(jid, []):
                    sid = stage["id"]
                    for task in self._tasks_by_stage.get(sid, []):
                        # responsible_for → actual person based on owner_role
                        owner_role = task["owner_role"]
                        if owner_role == "manager":
                            responsible_id = manager["id"]
                        elif owner_role == "buddy":
                            responsible_id = buddy["id"]
                        elif owner_role == "new_hire":
                            responsible_id = nh["id"]
                        else:   # HR or IT — use a senior manager as stand-in
                            responsible_id = self.rng.choice(managers_pool[:5])["id"]
                        self.e_responsible_for.append({
                            "from_id": task["id"],
                            "to_id": responsible_id,
                            "new_hire_id": nh["id"],
                        })

                        # completed — onboarding hires have partial progress
                        due = task["due_offset_days"]
                        if status == "onboarding":
                            if due <= days_in - 5:
                                task_status = "done"
                                ts = (today - timedelta(days=max(0, 14 - due))).isoformat()
                            elif due <= days_in:
                                task_status = "in_progress"
                                ts = ""
                            else:
                                task_status = "not_started"
                                ts = ""
                        else:
                            task_status = "not_started"
                            ts = ""
                        self.e_completed.append({
                            "from_id": nh["id"],
                            "to_id": task["id"],
                            "status": task_status,
                            "timestamp": ts,
                        })

                # Skills + interests
                skill_pool = PRACTICE_SKILLS.get(practice_id, [s["id"] for s in self.n_skills])
                for sid in self.rng.sample(skill_pool, min(2, len(skill_pool))):
                    self.e_expert_in.append({"from_id": nh["id"], "to_id": sid})
                for interest in self.rng.sample(self.n_interests, self.rng.randint(1, 2)):
                    self.e_interested_in.append({"from_id": nh["id"], "to_id": interest["id"]})
                for community in self.rng.sample(self.n_communities, self.rng.randint(1, 2)):
                    self.e_member_of_community.append({"from_id": nh["id"], "to_id": community["id"]})

                # Milestones for onboarding hires
                if status == "onboarding":
                    self.e_reaches.append({"from_id": nh["id"], "to_id": "milestone-it-ready"})
                    if self.rng.random() > 0.4:
                        self.e_reaches.append({"from_id": nh["id"], "to_id": "milestone-first-call"})

                # Pulse response for some onboarding hires
                if status == "onboarding" and self.rng.random() > 0.4:
                    pr_id = f"pulse-{len(self.n_pulse):04d}"
                    self.n_pulse.append({
                        "id": pr_id,
                        "moment": "day_14",
                        "score": self.rng.randint(7, 10),
                        "comment": self.rng.choice(PULSE_COMMENTS),
                    })
                    self.e_responded.append({"from_id": nh["id"], "to_id": pr_id})

                cohort_groups[cohort_idx].append(nh)
                self._new_hire_list.append(nh)
                self.n_persons.append(nh)

        # cohort_with edges (all pairs within each cohort)
        for group in cohort_groups:
            for i, a in enumerate(group):
                for b in group[i + 1:]:
                    self.e_cohort_with.append({"from_id": a["id"], "to_id": b["id"]})
                    self.e_cohort_with.append({"from_id": b["id"], "to_id": a["id"]})

    # -----------------------------------------------------------------------
    # Engagements
    # -----------------------------------------------------------------------

    def _gen_engagements(self):
        eng_templates = []
        if not self.args.no_llm:
            prompt = (
                f"Generate {self.args.num_engagements} fictional consulting engagement entries "
                "for an IT-services/management-consulting firm. Each needs a plausible fictional "
                "client company name and industry. "
                'Return ONLY a JSON array: [{"client":"...","industry":"..."}]. '
                "Industries: Financial Services, Healthcare, Retail, Energy, Government, Telecom, "
                "Manufacturing, Insurance, Life Sciences."
            )
            raw = _ollama(prompt, self.args.ollama_model)
            if raw:
                eng_templates = _parse_json_array(raw) or []

        active_staff = [p for p in self._active_persons]

        for i in range(self.args.num_engagements):
            if i < len(eng_templates):
                client = eng_templates[i].get("client", f"Client {i:03d} Corp")
                industry = eng_templates[i].get("industry", self.rng.choice(INDUSTRIES))
            else:
                client = f"{self.fake.company()} {self.rng.choice(['Corp', 'Group', 'Holdings', 'Ltd'])}"
                industry = self.rng.choice(INDUSTRIES)

            eid = f"engagement-{i:04d}"
            eng_status = self.rng.choices(["active", "closed"], weights=[75, 25])[0]
            self.n_engagements.append({"id": eid, "client": client, "industry": industry, "status": eng_status})

            # Staff 5–15 people
            team_size = self.rng.randint(5, min(15, len(active_staff)))
            staffed = self.rng.sample(active_staff, team_size)
            for person in staffed:
                self.e_staffed_on.append({"from_id": person["id"], "to_id": eid})

            # Engagement lead: Director or Partner preferred
            senior = [p for p in staffed if p["level"] in ("Partner", "Director", "Senior Manager")]
            lead = self.rng.choice(senior) if senior else self.rng.choice(staffed)
            self.e_leads_engagement.append({"from_id": lead["id"], "to_id": eid})

    # -----------------------------------------------------------------------
    # Derived edges
    # -----------------------------------------------------------------------

    def _materialize_collaborates_with(self):
        seen: set[tuple] = set()

        def add_pair(a: str, b: str, source: str):
            key = (min(a, b), max(a, b))
            if key not in seen:
                seen.add(key)
                self.e_collaborates_with.append({
                    "from_id": a, "to_id": b,
                    "source": source, "is_derived": True,
                })

        # From shared team membership
        team_members: dict[str, list[str]] = {}
        for edge in self.e_member_of:
            team_members.setdefault(edge["to_id"], []).append(edge["from_id"])
        for members in team_members.values():
            for j, a in enumerate(members):
                for b in members[j + 1:]:
                    add_pair(a, b, "team")

        # From shared engagement staffing
        eng_members: dict[str, list[str]] = {}
        for edge in self.e_staffed_on:
            eng_members.setdefault(edge["to_id"], []).append(edge["from_id"])
        for members in eng_members.values():
            for j, a in enumerate(members):
                for b in members[j + 1:]:
                    add_pair(a, b, "engagement")


# ---------------------------------------------------------------------------
# CSV / Cypher / manifest writers
# ---------------------------------------------------------------------------

def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]):
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_output(gen: Generator, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Node CSVs ---
    _write_csv(output_dir / "nodes_Person.csv", gen.n_persons, [
        "id", "name", "email", "status", "start_date", "level", "ladder_level",
        "location_id", "timezone", "languages", "tenure_months",
        "employment_type", "discoverable", "networking_opt_in", "work_style", "bio",
    ])
    _write_csv(output_dir / "nodes_Role.csv", gen.n_roles,
               ["id", "title", "role_family", "ladder_level"])
    _write_csv(output_dir / "nodes_Team.csv", gen.n_teams,
               ["id", "name", "function", "practice_id"])
    _write_csv(output_dir / "nodes_Practice.csv", gen.n_practices,
               ["id", "name"])
    _write_csv(output_dir / "nodes_Location.csv", gen.n_locations,
               ["id", "office", "geo", "timezone"])
    _write_csv(output_dir / "nodes_Engagement.csv", gen.n_engagements,
               ["id", "client", "industry", "status"])
    _write_csv(output_dir / "nodes_Community.csv", gen.n_communities,
               ["id", "type", "name", "blurb"])
    _write_csv(output_dir / "nodes_Journey.csv", gen.n_journeys,
               ["id", "type", "role_scope", "practice_scope"])
    _write_csv(output_dir / "nodes_Stage.csv", gen.n_stages,
               ["id", "name", "journey_id", "offset_days_start", "offset_days_end"])
    _write_csv(output_dir / "nodes_Task.csv", gen.n_tasks,
               ["id", "title", "category", "owner_role", "due_offset_days", "mandatory"])
    _write_csv(output_dir / "nodes_Milestone.csv", gen.n_milestones,
               ["id", "name", "description"])
    _write_csv(output_dir / "nodes_Skill.csv", gen.n_skills,
               ["id", "name", "category"])
    _write_csv(output_dir / "nodes_Interest.csv", gen.n_interests,
               ["id", "name"])
    _write_csv(output_dir / "nodes_PulseResponse.csv", gen.n_pulse,
               ["id", "moment", "score", "comment"])

    # --- Edge CSVs ---
    _write_csv(output_dir / "rels_reports_to.csv",        gen.e_reports_to,        ["from_id", "to_id"])
    _write_csv(output_dir / "rels_member_of.csv",          gen.e_member_of,          ["from_id", "to_id"])
    _write_csv(output_dir / "rels_part_of.csv",            gen.e_part_of,            ["from_id", "to_id"])
    _write_csv(output_dir / "rels_has_role.csv",           gen.e_has_role,           ["from_id", "to_id"])
    _write_csv(output_dir / "rels_based_at.csv",           gen.e_based_at,           ["from_id", "to_id"])
    _write_csv(output_dir / "rels_staffed_on.csv",         gen.e_staffed_on,         ["from_id", "to_id"])
    _write_csv(output_dir / "rels_leads_team.csv",         gen.e_leads_team,         ["from_id", "to_id"])
    _write_csv(output_dir / "rels_leads_practice.csv",     gen.e_leads_practice,     ["from_id", "to_id"])
    _write_csv(output_dir / "rels_leads_engagement.csv",   gen.e_leads_engagement,   ["from_id", "to_id"])
    _write_csv(output_dir / "rels_buddy_of.csv",           gen.e_buddy_of,           ["from_id", "to_id"])
    _write_csv(output_dir / "rels_mentor_of.csv",          gen.e_mentor_of,          ["from_id", "to_id"])
    _write_csv(output_dir / "rels_cohort_with.csv",        gen.e_cohort_with,        ["from_id", "to_id"])
    _write_csv(output_dir / "rels_member_of_community.csv",gen.e_member_of_community,["from_id", "to_id"])
    _write_csv(output_dir / "rels_expert_in.csv",          gen.e_expert_in,          ["from_id", "to_id"])
    _write_csv(output_dir / "rels_ask_me_about.csv",       gen.e_ask_me_about,       ["from_id", "to_id"])
    _write_csv(output_dir / "rels_interested_in.csv",      gen.e_interested_in,      ["from_id", "to_id"])
    _write_csv(output_dir / "rels_assigned_journey.csv",   gen.e_assigned_journey,   ["from_id", "to_id"])
    _write_csv(output_dir / "rels_has_stage.csv",          gen.e_has_stage,          ["from_id", "to_id"])
    _write_csv(output_dir / "rels_includes_task.csv",      gen.e_includes_task,      ["from_id", "to_id"])
    _write_csv(output_dir / "rels_responsible_for.csv",    gen.e_responsible_for,    ["from_id", "to_id", "new_hire_id"])
    _write_csv(output_dir / "rels_completed.csv",          gen.e_completed,          ["from_id", "to_id", "status", "timestamp"])
    _write_csv(output_dir / "rels_reaches.csv",            gen.e_reaches,            ["from_id", "to_id"])
    _write_csv(output_dir / "rels_responded.csv",          gen.e_responded,          ["from_id", "to_id"])
    _write_csv(output_dir / "rels_collaborates_with.csv",  gen.e_collaborates_with,  ["from_id", "to_id", "source", "is_derived"])


def write_load_cypher(output_dir: Path):
    lines = [
        "// MentorForge — Neo4j LOAD CSV script",
        "// Copy all CSV files into Neo4j's import directory, then run:",
        "//   cypher-shell -u neo4j -p <password> -f load.cypher",
        "// or paste into Neo4j Browser.",
        "",
        "// ── Constraints ────────────────────────────────────────────────────",
        "CREATE CONSTRAINT person_id     IF NOT EXISTS FOR (n:Person)        REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT role_id       IF NOT EXISTS FOR (n:Role)          REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT team_id       IF NOT EXISTS FOR (n:Team)          REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT practice_id   IF NOT EXISTS FOR (n:Practice)      REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT location_id   IF NOT EXISTS FOR (n:Location)      REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT engagement_id IF NOT EXISTS FOR (n:Engagement)    REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT community_id  IF NOT EXISTS FOR (n:Community)     REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT journey_id    IF NOT EXISTS FOR (n:Journey)       REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT stage_id      IF NOT EXISTS FOR (n:Stage)         REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT task_id       IF NOT EXISTS FOR (n:Task)          REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT milestone_id  IF NOT EXISTS FOR (n:Milestone)     REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT skill_id      IF NOT EXISTS FOR (n:Skill)         REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT interest_id   IF NOT EXISTS FOR (n:Interest)      REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT pulse_id      IF NOT EXISTS FOR (n:PulseResponse) REQUIRE n.id IS UNIQUE;",
        "",
        "// ── Nodes ────────────────────────────────────────────────────────────",
    ]

    node_loads = [
        ("Person", "nodes_Person.csv",
         "CREATE (:Person {id:row.id, name:row.name, email:row.email, status:row.status, "
         "start_date:row.start_date, level:row.level, ladder_level:row.ladder_level, "
         "location_id:row.location_id, timezone:row.timezone, languages:row.languages, "
         "tenure_months:toInteger(row.tenure_months), employment_type:row.employment_type, "
         "discoverable:row.discoverable='True', networking_opt_in:row.networking_opt_in='True', "
         "work_style:row.work_style, bio:row.bio})"),
        ("Role", "nodes_Role.csv",
         "CREATE (:Role {id:row.id, title:row.title, role_family:row.role_family, ladder_level:row.ladder_level})"),
        ("Team", "nodes_Team.csv",
         "CREATE (:Team {id:row.id, name:row.name, function:row.function})"),
        ("Practice", "nodes_Practice.csv",
         "CREATE (:Practice {id:row.id, name:row.name})"),
        ("Location", "nodes_Location.csv",
         "CREATE (:Location {id:row.id, office:row.office, geo:row.geo, timezone:row.timezone})"),
        ("Engagement", "nodes_Engagement.csv",
         "CREATE (:Engagement {id:row.id, client:row.client, industry:row.industry, status:row.status})"),
        ("Community", "nodes_Community.csv",
         "CREATE (:Community {id:row.id, type:row.type, name:row.name, blurb:row.blurb})"),
        ("Journey", "nodes_Journey.csv",
         "CREATE (:Journey {id:row.id, type:row.type, role_scope:row.role_scope, practice_scope:row.practice_scope})"),
        ("Stage", "nodes_Stage.csv",
         "CREATE (:Stage {id:row.id, name:row.name, journey_id:row.journey_id, "
         "offset_days_start:toInteger(row.offset_days_start), offset_days_end:toInteger(row.offset_days_end)})"),
        ("Task", "nodes_Task.csv",
         "CREATE (:Task {id:row.id, title:row.title, category:row.category, owner_role:row.owner_role, "
         "due_offset_days:toInteger(row.due_offset_days), mandatory:row.mandatory='True'})"),
        ("Milestone", "nodes_Milestone.csv",
         "CREATE (:Milestone {id:row.id, name:row.name, description:row.description})"),
        ("Skill", "nodes_Skill.csv",
         "CREATE (:Skill {id:row.id, name:row.name, category:row.category})"),
        ("Interest", "nodes_Interest.csv",
         "CREATE (:Interest {id:row.id, name:row.name})"),
        ("PulseResponse", "nodes_PulseResponse.csv",
         "CREATE (:PulseResponse {id:row.id, moment:row.moment, score:toInteger(row.score), comment:row.comment})"),
    ]

    for label, filename, create_clause in node_loads:
        lines += [
            f"LOAD CSV WITH HEADERS FROM 'file:///{filename}' AS row",
            create_clause + ";",
            "",
        ]

    lines.append("// ── Relationships ───────────────────────────────────────────────────")

    rel_loads = [
        ("reports_to",         "rels_reports_to.csv",         "Person", "Person",     "REPORTS_TO",         ""),
        ("member_of",          "rels_member_of.csv",          "Person", "Team",       "MEMBER_OF",          ""),
        ("part_of",            "rels_part_of.csv",            "Team",   "Practice",   "PART_OF",            ""),
        ("has_role",           "rels_has_role.csv",           "Person", "Role",       "HAS_ROLE",           ""),
        ("based_at",           "rels_based_at.csv",           "Person", "Location",   "BASED_AT",           ""),
        ("staffed_on",         "rels_staffed_on.csv",         "Person", "Engagement", "STAFFED_ON",         ""),
        ("leads_team",         "rels_leads_team.csv",         "Person", "Team",       "LEADS",              ""),
        ("leads_practice",     "rels_leads_practice.csv",     "Person", "Practice",   "LEADS",              ""),
        ("leads_engagement",   "rels_leads_engagement.csv",   "Person", "Engagement", "LEADS",              ""),
        ("buddy_of",           "rels_buddy_of.csv",           "Person", "Person",     "BUDDY_OF",           ""),
        ("mentor_of",          "rels_mentor_of.csv",          "Person", "Person",     "MENTOR_OF",          ""),
        ("cohort_with",        "rels_cohort_with.csv",        "Person", "Person",     "COHORT_WITH",        ""),
        ("member_of_community","rels_member_of_community.csv","Person", "Community",  "MEMBER_OF_COMMUNITY",""),
        ("expert_in",          "rels_expert_in.csv",          "Person", "Skill",      "EXPERT_IN",          ""),
        ("ask_me_about",       "rels_ask_me_about.csv",       "Person", "Skill",      "ASK_ME_ABOUT",       ""),
        ("interested_in",      "rels_interested_in.csv",      "Person", "Interest",   "INTERESTED_IN",      ""),
        ("assigned_journey",   "rels_assigned_journey.csv",   "Person", "Journey",    "ASSIGNED_JOURNEY",   ""),
        ("has_stage",          "rels_has_stage.csv",          "Journey","Stage",      "HAS_STAGE",          ""),
        ("includes_task",      "rels_includes_task.csv",      "Stage",  "Task",       "INCLUDES_TASK",      ""),
        ("reaches",            "rels_reaches.csv",            "Person", "Milestone",  "REACHES",            ""),
        ("responded",          "rels_responded.csv",          "Person", "PulseResponse","RESPONDED",        ""),
    ]

    for name, filename, from_label, to_label, rel_type, props in rel_loads:
        lines += [
            f"LOAD CSV WITH HEADERS FROM 'file:///{filename}' AS row",
            f"MATCH (a:{from_label} {{id:row.from_id}}), (b:{to_label} {{id:row.to_id}})",
            f"CREATE (a)-[:{rel_type}]->(b);",
            "",
        ]

    # Edges with properties
    lines += [
        "LOAD CSV WITH HEADERS FROM 'file:///rels_responsible_for.csv' AS row",
        "MATCH (t:Task {id:row.from_id}), (p:Person {id:row.to_id})",
        "CREATE (t)-[:RESPONSIBLE_FOR {new_hire_id:row.new_hire_id}]->(p);",
        "",
        "LOAD CSV WITH HEADERS FROM 'file:///rels_completed.csv' AS row",
        "MATCH (p:Person {id:row.from_id}), (t:Task {id:row.to_id})",
        "CREATE (p)-[:COMPLETED {status:row.status, timestamp:row.timestamp}]->(t);",
        "",
        "LOAD CSV WITH HEADERS FROM 'file:///rels_collaborates_with.csv' AS row",
        "MATCH (a:Person {id:row.from_id}), (b:Person {id:row.to_id})",
        "CREATE (a)-[:COLLABORATES_WITH {source:row.source, is_derived:row.is_derived='True'}]->(b);",
        "",
        "// ── Verification ─────────────────────────────────────────────────────",
        "// Run these to confirm expected counts:",
        "// MATCH (n:Person)   RETURN count(n) AS persons;          // ~400",
        "// MATCH (n:Task)     RETURN count(n) AS tasks;",
        "// MATCH ()-[:REPORTS_TO]->() RETURN count(*) AS reports_to;",
        "// MATCH (p:Person {status:'onboarding'}) RETURN p.name, p.start_date LIMIT 5;",
    ]

    with open(output_dir / "load.cypher", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_manifest(gen: Generator, output_dir: Path, args):
    today = date.today().isoformat()
    all_counts = {
        "persons":             len(gen.n_persons),
        "active_staff":        len(gen._active_persons),
        "new_hires":           len(gen._new_hire_list),
        "practices":           len(gen.n_practices),
        "teams":               len(gen.n_teams),
        "engagements":         len(gen.n_engagements),
        "communities":         len(gen.n_communities),
        "skills":              len(gen.n_skills),
        "interests":           len(gen.n_interests),
        "journeys":            len(gen.n_journeys),
        "stages":              len(gen.n_stages),
        "tasks":               len(gen.n_tasks),
        "milestones":          len(gen.n_milestones),
        "pulse_responses":     len(gen.n_pulse),
        "rels_reports_to":     len(gen.e_reports_to),
        "rels_member_of":      len(gen.e_member_of),
        "rels_staffed_on":     len(gen.e_staffed_on),
        "rels_buddy_of":       len(gen.e_buddy_of),
        "rels_cohort_with":    len(gen.e_cohort_with),
        "rels_collaborates_with": len(gen.e_collaborates_with),
        "rels_completed":      len(gen.e_completed),
    }

    manifest = {
        "generated_at": today,
        "seed": args.seed,
        "config": {
            "num_people":      args.num_people,
            "num_new_hires":   args.num_new_hires,
            "num_engagements": args.num_engagements,
            "no_llm":          args.no_llm,
            "ollama_model":    args.ollama_model,
        },
        "counts": all_counts,
        "practices": [{"id": p["id"], "name": p["name"]} for p in gen.n_practices],
        "teams": [{"id": t["id"], "name": t["name"], "practice_id": t["practice_id"]}
                  for t in gen.n_teams],
        "new_hires": [
            {
                "id": nh["id"],
                "name": nh["name"],
                "email": nh["email"],
                "status": nh["status"],
                "start_date": nh["start_date"],
                "level": nh["level"],
                "practice_id": nh["_practice_id"],
                "team_id": nh.get("_team_id", ""),
            }
            for nh in gen._new_hire_list
        ],
        "people": [
            {"id": p["id"], "name": p["name"], "email": p["email"],
             "level": p["level"], "practice_id": p["_practice_id"]}
            for p in gen.n_persons
        ],
        "engagements": [
            {"id": e["id"], "client": e["client"], "industry": e["industry"], "status": e["status"]}
            for e in gen.n_engagements
        ],
        "communities": [
            {"id": c["id"], "type": c["type"], "name": c["name"]}
            for c in gen.n_communities
        ],
        "skills": [{"id": s["id"], "name": s["name"], "category": s["category"]}
                   for s in gen.n_skills],
    }

    with open(output_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify(gen: Generator) -> list[str]:
    """Return list of failing assertions (empty = all pass)."""
    failures = []

    # DAG check on reports_to
    children: dict[str, list[str]] = {}
    for edge in gen.e_reports_to:
        children.setdefault(edge["from_id"], []).append(edge["to_id"])

    def has_cycle(node, visited, stack):
        visited.add(node)
        stack.add(node)
        for child in children.get(node, []):
            if child not in visited:
                if has_cycle(child, visited, stack):
                    return True
            elif child in stack:
                return True
        stack.discard(node)
        return False

    visited, stack = set(), set()
    for node_id in set(e["from_id"] for e in gen.e_reports_to):
        if node_id not in visited:
            if has_cycle(node_id, visited, stack):
                failures.append("reports_to contains a cycle")
                break

    # Pyramid sanity: more analysts than partners
    analysts = len(gen._persons_by_level.get("Analyst", []))
    partners = len(gen._persons_by_level.get("Partner", []))
    if analysts <= partners:
        failures.append(f"Pyramid inverted: {analysts} analysts, {partners} partners")

    # Every new hire has buddy, manager, journey
    nh_ids = {nh["id"] for nh in gen._new_hire_list}
    nh_has_buddy = {e["from_id"] for e in gen.e_buddy_of} & nh_ids
    nh_has_manager = {e["from_id"] for e in gen.e_reports_to} & nh_ids
    nh_has_journey = {e["from_id"] for e in gen.e_assigned_journey} & nh_ids
    missing_buddy = nh_ids - nh_has_buddy
    missing_manager = nh_ids - nh_has_manager
    missing_journey = nh_ids - nh_has_journey
    if missing_buddy:
        failures.append(f"{len(missing_buddy)} new hires missing buddy_of")
    if missing_manager:
        failures.append(f"{len(missing_manager)} new hires missing reports_to")
    if missing_journey:
        failures.append(f"{len(missing_journey)} new hires missing assigned_journey")

    # Consent attrs present on all persons (spot-check: field exists in CSV)
    for p in gen.n_persons[:5]:
        if "discoverable" not in p or "networking_opt_in" not in p:
            failures.append("Person missing consent attrs (discoverable / networking_opt_in)")
            break

    # manifest.json coherence: all new hire IDs appear in manifest people list
    nh_ids_in_people = {p["id"] for p in gen._new_hire_list}
    if not nh_ids_in_people.issubset({p["id"] for p in gen.n_persons}):
        failures.append("New hire IDs not present in persons list")

    return failures


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="MentorForge synthetic org/people graph generator.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--num-people",      type=int, default=400,
                   help="Total headcount (includes new hires)")
    p.add_argument("--num-new-hires",   type=int, default=30,
                   help="New-hire cohort size (1–2 cohorts)")
    p.add_argument("--num-engagements", type=int, default=20,
                   help="Number of client engagements")
    p.add_argument("--seed",            type=int, default=42,
                   help="Random seed for deterministic output")
    p.add_argument("--output-dir",      type=str, default="output",
                   help="Directory for CSVs, load.cypher, manifest.json")
    p.add_argument("--ollama-model",    type=str, default="llama3.3",
                   help="Ollama model for narrative generation")
    p.add_argument("--no-llm",          action="store_true",
                   help="Skip Ollama; use templated values only (fast, offline)")
    return p.parse_args()


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)

    print(f"MentorForge org generator — seed={args.seed}, "
          f"people={args.num_people}, new_hires={args.num_new_hires}, "
          f"engagements={args.num_engagements}, llm={'off' if args.no_llm else 'on'}")

    gen = Generator(args)
    gen.run()

    print("Verifying...")
    failures = verify(gen)
    if failures:
        print("  FAIL:")
        for f in failures:
            print(f"    ✗ {f}")
        sys.exit(1)
    else:
        print("  All checks passed.")

    print(f"Writing output to {output_dir}/...")
    write_output(gen, output_dir)
    write_load_cypher(output_dir)
    write_manifest(gen, output_dir, args)

    counts = {
        "persons": len(gen.n_persons),
        "new_hires": len(gen._new_hire_list),
        "engagements": len(gen.n_engagements),
        "tasks": len(gen.n_tasks),
        "collaborates_with": len(gen.e_collaborates_with),
    }
    print("Done.")
    print(f"  {counts['persons']} persons  ({counts['new_hires']} new hires)")
    print(f"  {counts['engagements']} engagements")
    print(f"  {counts['tasks']} tasks across all journey templates")
    print(f"  {counts['collaborates_with']} collaborates_with edges (derived)")
    print(f"  CSVs + load.cypher + manifest.json → {output_dir}/")


if __name__ == "__main__":
    main()
