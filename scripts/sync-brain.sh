#!/bin/bash
# Pulls the brain artifacts Claude Code needs into docs/.
# Run at session start: ! ./scripts/sync-brain.sh
# The brain lives in the local Obsidian vault; docs/ is the stable mirror for Claude Code.

set -euo pipefail

BRAIN="$HOME/Workspace/Obsidian/Harsha_Brain/04 Projects/MentorForge"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOCS="$REPO_ROOT/docs"

FILES=(
  "CLAUDE.md"
  "01 Architecture/(C) ADR Backlog.md"
  "06 Iteration Logs/log.md"
)

# Individual ADRs — add entries here as they are written in the brain
ADRS=(
  "01 Architecture/(C) ADR-001 — Hybrid Architecture - Cloud Reasoning, On-Premise Corpus.md"
)

echo "Syncing brain → docs/"

for f in "${FILES[@]}" "${ADRS[@]}"; do
  src="$BRAIN/$f"
  dest="$DOCS/$(basename "$f")"
  if [ -f "$src" ]; then
    cp "$src" "$dest"
    echo "  ✓ $(basename "$f")"
  else
    echo "  ✗ MISSING: $f"
  fi
done

echo "Done."
