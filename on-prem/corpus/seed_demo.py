#!/usr/bin/env python3
"""
seed_demo.py — Assembles the full demo corpus into silver/ for GraphRAG ingestion.

Runs the full corpus assembly pipeline:
  1. Validates TASK-001 output + cast patch applied
  2. Copies hero docs → silver/
  3. Runs generate_corpus.py → silver/ (bulk docs)
  4. Writes _index.json — ADR-019 provenance index for every file
  5. Prints GraphRAG next-step instructions

Usage:
    python seed_demo.py [--no-llm] [--silver-dir silver/]
    python seed_demo.py --dry-run   # just validate and preview
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

CORPUS_DIR  = Path(__file__).parent
DATAGEN_DIR = CORPUS_DIR.parent / "datagen"
HERO_DIR    = CORPUS_DIR / "hero"
GENERATED_DIR = CORPUS_DIR / "generated"


def check_prerequisites(skip_cast_check: bool = False):
    manifest_path = DATAGEN_DIR / "output" / "manifest.json"
    if not manifest_path.exists():
        sys.exit("TASK-001 output not found. Run: cd on-prem/datagen && python3 generate.py --no-llm")

    manifest = json.loads(manifest_path.read_text())
    if not skip_cast_check and "demo_cast" not in manifest:
        sys.exit("Cast not patched. Run: cd on-prem/corpus && python3 patch_cast.py")

    return manifest


def collect_hero_docs() -> list[Path]:
    docs = []
    for path in HERO_DIR.rglob("*.md"):
        docs.append(path)
    return sorted(docs)


def parse_frontmatter(content: str) -> dict:
    """Extract the source/provenance/content_meta YAML frontmatter as a dict (best-effort)."""
    if not content.startswith("---"):
        return {}
    end = content.find("\n---", 3)
    if end == -1:
        return {}
    fm_block = content[3:end].strip()
    result = {}
    # Very simple key: value extraction — no full YAML parser needed
    for line in fm_block.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip()
    return result


def copy_to_silver(docs: list[Path], silver_dir: Path, prefix: str = "") -> list[dict]:
    """Copy docs to silver/, return provenance index entries."""
    index_entries = []
    for doc in docs:
        # Flatten subdirectory into filename: hero/erg/women-in-tech.md → erg-women-in-tech.md
        rel = doc.relative_to(HERO_DIR if HERO_DIR in doc.parents or doc.parent == HERO_DIR else GENERATED_DIR)
        flat_name = prefix + str(rel).replace(os.sep, "-")
        dest = silver_dir / flat_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(doc, dest)

        content = doc.read_text(encoding="utf-8")
        fm = parse_frontmatter(content)

        index_entries.append({
            "file": flat_name,
            "source_path": str(doc.relative_to(CORPUS_DIR)),
            "source_system": fm.get("source", ""),
            "type": fm.get("content_meta", ""),
            "title": fm.get("content_meta", flat_name),
            "classification": fm.get("classification", ""),
        })

    return index_entries


def run_generate_corpus(silver_dir: Path, no_llm: bool, ollama_model: str):
    """Run generate_corpus.py to produce bulk docs."""
    generated_dir = silver_dir / "_bulk"
    cmd = [
        sys.executable, str(CORPUS_DIR / "generate_corpus.py"),
        "--output-dir", str(generated_dir),
    ]
    if no_llm:
        cmd.append("--no-llm")
    if ollama_model:
        cmd += ["--ollama-model", ollama_model]

    print(f"  Running generate_corpus.py → {generated_dir}/...")
    result = subprocess.run(cmd, capture_output=False, text=True)
    if result.returncode != 0:
        print(f"  [WARN] generate_corpus.py exited with code {result.returncode}")

    # Collect generated docs
    return list(generated_dir.rglob("*.md")) if generated_dir.exists() else []


def write_index(index_entries: list[dict], silver_dir: Path, manifest: dict):
    index = {
        "generated_at": "2026-05-31",
        "company": "Northstar Consulting",
        "total_docs": len(index_entries),
        "demo_cast": manifest.get("demo_cast", {}),
        "docs": index_entries,
    }
    index_path = silver_dir / "_index.json"
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(f"  Wrote provenance index: {index_path}")


def print_graphrag_instructions(silver_dir: Path):
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║  Next: GraphRAG bake                                                         ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Prerequisites (from readiness checklist):                                   ║
║    ✓ TASK-001 org graph loaded into Neo4j (load.cypher)                      ║
║    □ Docker Compose up: Neo4j + Ollama + GraphRAG                            ║
║    □ Ollama model pulled: ollama pull llama3.3:70b                           ║
║                                                                              ║
║  1. Copy corpus to GraphRAG input dir:                                       ║
║     docker cp silver/. mentorforge-graphrag-1:/app/input/                   ║
║                                                                              ║
║  2. Run the GraphRAG index:                                                  ║
║     docker exec mentorforge-graphrag-1 python -m graphrag index \\           ║
║       --root /app                                                            ║
║                                                                              ║
║  3. Monitor bake time (Full Standard on one VM ~ hours for 1000+ docs):     ║
║     docker logs -f mentorforge-graphrag-1                                    ║
║                                                                              ║
║  4. After bake — run validation queries (see README):                        ║
║     Smoke test: global search "Who at Northstar knows Unity Catalog?"        ║
║     Story 2:    graph_traverse person=Dana Okafor depth=2                   ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")


def parse_args():
    p = argparse.ArgumentParser(
        description="Assemble demo corpus into silver/ for GraphRAG ingestion.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--silver-dir",   default="silver",   help="Output dir for GraphRAG input")
    p.add_argument("--no-llm",       action="store_true", help="Skip Ollama in corpus generator")
    p.add_argument("--ollama-model", default="llama3.3",  help="Ollama model")
    p.add_argument("--dry-run",      action="store_true", help="Validate only, do not write")
    p.add_argument("--skip-cast-check", action="store_true", help="Skip demo_cast manifest check")
    return p.parse_args()


def main():
    args = parse_args()
    silver_dir = Path(args.silver_dir)

    print("MentorForge corpus assembler")
    print(f"  Silver output: {silver_dir.resolve()}")

    print("  Checking prerequisites...")
    manifest = check_prerequisites(skip_cast_check=args.skip_cast_check)

    hero_docs = collect_hero_docs()
    print(f"  Found {len(hero_docs)} hero docs in hero/")

    if args.dry_run:
        print("\nDry run — no files written.")
        print(f"  Hero docs: {len(hero_docs)}")
        for d in hero_docs:
            print(f"    {d.relative_to(CORPUS_DIR)}")
        return

    # Create silver dir
    silver_dir.mkdir(parents=True, exist_ok=True)

    # Copy hero docs
    print("  Copying hero docs → silver/...")
    hero_index = copy_to_silver(hero_docs, silver_dir, prefix="hero-")

    # Generate bulk corpus
    bulk_docs = run_generate_corpus(silver_dir, no_llm=args.no_llm, ollama_model=args.ollama_model)

    # Build index entries for bulk docs
    bulk_index = []
    for doc in bulk_docs:
        content = doc.read_text(encoding="utf-8")
        fm = parse_frontmatter(content)
        bulk_index.append({
            "file": str(doc.relative_to(silver_dir)),
            "source_path": doc.name,
            "source_system": fm.get("source", "generated"),
            "type": fm.get("content_meta", ""),
            "title": fm.get("content_meta", doc.stem),
            "classification": fm.get("classification", "internal"),
        })

    all_index = hero_index + bulk_index
    write_index(all_index, silver_dir, manifest)

    total = len(all_index)
    print(f"\n  Corpus assembled: {total} docs in {silver_dir}/")
    print(f"    Hero docs: {len(hero_index)}")
    print(f"    Bulk docs: {len(bulk_index)}")

    print_graphrag_instructions(silver_dir)


if __name__ == "__main__":
    main()
