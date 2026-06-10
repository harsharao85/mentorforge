#!/usr/bin/env python3
"""
generate_corpus.py — Bulk corpus generator for MentorForge demo.

Uses Ollama + manifest.json to generate policies, runbooks, FAQs, and
retrospectives that reference the demo cast (Northstar Consulting).
In --no-llm mode, writes templated placeholder docs so the pipeline
can be tested without Ollama running.

Usage:
    python generate_corpus.py [--no-llm] [--output-dir generated/]
    python generate_corpus.py --count 50 --seed 42
"""

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path
from typing import Optional

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

DATAGEN_OUTPUT = Path(__file__).parent.parent / "datagen" / "output"

# ---------------------------------------------------------------------------
# Doc templates — each is a (filename_slug, source_system, doc_type, prompt_fn)
# ---------------------------------------------------------------------------

def _ollama(prompt: str, model: str) -> Optional[str]:
    if not _HAS_REQUESTS:
        return None
    try:
        resp = _requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as exc:
        print(f"  [WARN] Ollama unavailable ({exc})", file=sys.stderr)
        return None


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _frontmatter(source_system: str, source_id: str, author: str, doc_type: str, title: str, tags: list[str]) -> str:
    tag_str = ", ".join(tags)
    return f"""---
source: {{system: {source_system}, instance: northstar-{source_system}, source_id: "{source_id}", connector_version: "1.0"}}
provenance: {{author: "{author}", owner: "Northstar Consulting", ingested_at: "2026-05-01"}}
classification: {{sensitivity: internal, acl: [all-employees]}}
content_meta: {{type: {doc_type}, title: "{title}", tags: [{tag_str}]}}
---

"""


# ---- Templates used in --no-llm mode ----

def _template_policy(title: str, practice: str, engagement: str) -> str:
    return f"""# {title}

**Owner:** {practice} Practice, Northstar Consulting
**Applicability:** All staff on {engagement} and similar engagements

## Purpose

This policy establishes requirements for {practice.lower()} work at Northstar Consulting. All staff are expected to adhere to these guidelines on client engagements.

## Requirements

1. All deliverables must follow the {practice} practice standards.
2. Client data handling must comply with the relevant regulatory framework.
3. Documentation must be complete before engagement closeout.

## Contacts

Questions → {practice} Practice Lead or your engagement manager.
"""


def _template_runbook(title: str, practice: str, team: str) -> str:
    return f"""# {title}

**Team:** {team}
**Practice:** {practice}

## Overview

This runbook covers standard operating procedures for the {team} team at Northstar Consulting.

## Steps

1. Verify environment access before starting any work.
2. Follow the standard deployment checklist.
3. Log all changes in the engagement tracking system.
4. Notify the engagement lead of any anomalies.

## Escalation

Issues that cannot be resolved within 2 hours should be escalated to the engagement lead.
"""


def _template_faq(practice: str, engagement: str) -> str:
    return f"""# Frequently Asked Questions — {practice} at Northstar

## General

**Q: Where do I find the engagement runbook?**
A: Runbooks are stored in the engagement Confluence space. Ask your manager for the link.

**Q: Who approves access to client systems?**
A: All access requests route through the engagement lead.

**Q: What tooling does Northstar use for {practice.lower()} engagements?**
A: The {practice} practice uses a standardized stack documented in the {practice} Practice Playbook.

## Onboarding on {engagement}

**Q: What should I read first when joining {engagement}?**
A: Start with the engagement runbook and the practice playbook. Then shadow the team's standups for at least two days before taking on deliverables.

**Q: Who is my point of contact for day-to-day questions?**
A: Your manager and buddy are your primary contacts. Escalate to the engagement lead for client-specific questions.
"""


# ---- LLM-powered generator ----

def _llm_doc(prompt_fn, model: str, cast: dict) -> Optional[str]:
    prompt = prompt_fn(cast)
    return _ollama(prompt, model)


def build_doc_specs(manifest: dict) -> list[dict]:
    """Return a list of doc specs to generate."""
    cast = manifest.get("demo_cast", {})
    people = {p["name"]: p for p in manifest.get("people", [])
              if p["name"] in ("Ben Okonkwo", "Tom Rivera", "Sarah Chen",
                               "Dana Okafor", "Lena Hofer", "Priya Nair",
                               "Marcus Lee", "Aisha Rahman")}

    practices = [p["name"] for p in manifest.get("practices", [])]
    teams     = [t["name"] for t in manifest.get("teams", [])]
    engs      = {e["id"]: e["client"] for e in manifest.get("engagements", [])}

    atlas_id    = cast.get("engagements", {}).get("atlas_health", "")
    northwind_id= cast.get("engagements", {}).get("northwind", "")
    meridian_id = cast.get("engagements", {}).get("meridian", "")
    helios_id   = cast.get("engagements", {}).get("helios", "")

    atlas    = engs.get(atlas_id, "Atlas-Health")
    northwind= engs.get(northwind_id, "Northwind")
    meridian = engs.get(meridian_id, "Meridian")
    helios   = engs.get(helios_id, "Helios")

    specs = []

    # --- Policies (S3 mock) ---
    for practice in practices:
        specs.append({
            "slug":    f"policy-{_slug(practice)}-standards",
            "source":  "s3",
            "type":    "policy",
            "title":   f"{practice} Practice Standards Policy",
            "tags":    [_slug(practice), "policy", "standards"],
            "author":  "GRC & Compliance",
            "template": lambda p=practice: _template_policy(f"{p} Practice Standards Policy", p, "client engagements"),
            "llm_prompt": lambda cast, p=practice: (
                f"Write a 400-word internal policy document for Northstar Consulting's {p} practice. "
                "Include: purpose, scope, key requirements, compliance obligations, and contacts. "
                "Reference the consulting firm Northstar Consulting. Be professional and realistic."
            ),
        })

    # --- Runbooks (Confluence mock) ---
    for team in teams[:8]:  # limit volume
        practice = next((p for p in practices if _slug(p) in _slug(team)), practices[0])
        specs.append({
            "slug":    f"runbook-{_slug(team)}",
            "source":  "confluence",
            "type":    "runbook",
            "title":   f"{team} — Standard Runbook",
            "tags":    [_slug(team), "runbook", _slug(practice)],
            "author":  "Team Lead",
            "template": lambda t=team, p=practice: _template_runbook(f"{t} Standard Runbook", p, t),
            "llm_prompt": lambda cast, t=team, p=practice: (
                f"Write a 350-word internal runbook for the '{t}' team at Northstar Consulting ({p} practice). "
                "Include: overview, standard procedures, escalation path. "
                "Professional consulting firm tone."
            ),
        })

    # --- FAQs (KB mock) ---
    for practice in practices:
        specs.append({
            "slug":    f"faq-{_slug(practice)}-onboarding",
            "source":  "kb",
            "type":    "kb",
            "title":   f"FAQ — {practice} Onboarding",
            "tags":    [_slug(practice), "faq", "onboarding"],
            "author":  "Practice Operations",
            "template": lambda p=practice, e=atlas: _template_faq(p, e),
            "llm_prompt": lambda cast, p=practice: (
                f"Write a 300-word FAQ document for new Northstar Consulting employees joining the {p} practice. "
                "Cover common questions about tools, processes, access, and onboarding. "
                "Use Q&A format. Professional tone."
            ),
        })

    # --- Engagement-specific docs (SharePoint mock) ---
    for eng_name, practice, engagement_context in [
        (atlas,    "Data",     "HIPAA-regulated healthcare payer data platform"),
        (northwind,"Cloud",    "UK retail e-commerce cloud migration"),
        (meridian, "Data",     "Technology client data platform and Unity Catalog migration"),
        (helios,   "Strategy", "Management consulting transformation engagement"),
    ]:
        specs.append({
            "slug":    f"engagement-brief-{_slug(eng_name)}",
            "source":  "sharepoint",
            "type":    "methodology",
            "title":   f"{eng_name} — Engagement Brief",
            "tags":    [_slug(eng_name), "engagement", "brief"],
            "author":  "Engagement Lead",
            "template": lambda e=eng_name, p=practice, ctx=engagement_context: (
                f"# {e} — Engagement Brief\n\n"
                f"**Practice:** {p}\n**Context:** {ctx}\n\n"
                f"## Overview\n\nThis engagement positions Northstar Consulting as the strategic partner "
                f"for {e}'s {ctx.lower()}. The work spans assessment, design, build, and transition phases.\n\n"
                f"## Key Objectives\n\n1. Deliver the core {p.lower()} platform on time and on budget.\n"
                f"2. Transfer knowledge so the client team can operate independently.\n"
                f"3. Establish Northstar as the preferred long-term {p.lower()} partner.\n\n"
                f"## Contacts\n\nEngagement lead and practice lead are the primary escalation path.\n"
            ),
            "llm_prompt": lambda cast, e=eng_name, p=practice, ctx=engagement_context: (
                f"Write a 350-word engagement brief for Northstar Consulting's {e} engagement. "
                f"Context: {ctx}. Practice: {p}. "
                "Include: client overview, engagement objectives, team structure, key milestones. "
                "Professional consulting tone."
            ),
        })

    # --- GitHub-flavored technical docs ---
    specs.append({
        "slug":    "github-data-pipeline-standards",
        "source":  "github",
        "type":    "code",
        "title":   "Data Pipeline Development Standards",
        "tags":    ["data", "pipeline", "standards", "github", "python"],
        "author":  "Data Practice Engineering",
        "template": lambda: (
            "# Data Pipeline Development Standards\n\n"
            "**Repo:** northstar-consulting/data-standards\n\n"
            "## Code Standards\n\n"
            "- All pipelines must use Python 3.11+\n"
            "- pytest coverage ≥ 80% on all new code\n"
            "- Black + Ruff for formatting and linting\n"
            "- Type hints on all public functions\n\n"
            "## Databricks Patterns\n\n"
            "- Use Delta Live Tables for streaming pipelines\n"
            "- Unity Catalog for all data governance (see Meridian Unity Catalog Retrospective)\n"
            "- Contact Dana Okafor for Unity Catalog architecture questions\n\n"
            "## Pull Request Requirements\n\n"
            "- One reviewer minimum; two for production code\n"
            "- No self-merges\n"
            "- All pipeline changes must include a runbook update\n"
        ),
        "llm_prompt": lambda cast: (
            "Write a 350-word technical README for Northstar Consulting's data pipeline standards repository. "
            "Include: code standards, Databricks patterns, CI/CD requirements, pull request norms. "
            "Reference Dana Okafor as the Unity Catalog expert. Technical tone."
        ),
    })

    return specs


def generate(args):
    manifest_path = DATAGEN_OUTPUT / "manifest.json"
    if not manifest_path.exists():
        sys.exit(f"manifest.json not found at {manifest_path}. Run generate.py and patch_cast.py first.")

    manifest = json.loads(manifest_path.read_text())
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    specs = build_doc_specs(manifest)
    rng = random.Random(args.seed)
    if args.count and args.count < len(specs):
        specs = rng.sample(specs, args.count)

    print(f"  Generating {len(specs)} bulk docs → {output_dir}/...")

    written = 0
    for spec in specs:
        slug = spec["slug"]
        path = output_dir / f"{slug}.md"

        content = None
        if not args.no_llm:
            llm_prompt_fn = spec.get("llm_prompt")
            if llm_prompt_fn:
                raw = _ollama(llm_prompt_fn(manifest.get("demo_cast", {})), args.ollama_model)
                if raw:
                    content = raw

        if content is None:
            tmpl = spec.get("template")
            content = tmpl() if tmpl else f"# {spec['title']}\n\nContent pending.\n"

        fm = _frontmatter(
            source_system=spec["source"],
            source_id=slug.upper().replace("-", "_"),
            author=spec["author"],
            doc_type=spec["type"],
            title=spec["title"],
            tags=spec["tags"],
        )

        path.write_text(fm + content, encoding="utf-8")
        written += 1
        print(f"    [{written}/{len(specs)}] {slug}.md")

    print(f"  Done. {written} docs written to {output_dir}/")
    return written


def parse_args():
    p = argparse.ArgumentParser(
        description="Generate bulk corpus docs for MentorForge demo.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--output-dir",   default="generated", help="Output directory")
    p.add_argument("--count",        type=int, default=None, help="Limit to N docs (default: all)")
    p.add_argument("--seed",         type=int, default=42,   help="Random seed")
    p.add_argument("--ollama-model", default="llama3.3",     help="Ollama model")
    p.add_argument("--no-llm",       action="store_true",    help="Use templates only")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    generate(args)
