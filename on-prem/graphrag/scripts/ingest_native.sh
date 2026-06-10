#!/bin/bash
# Native GraphRAG bake for Apple Silicon (Metal Ollama, no containerized Ollama).
# GraphRAG 3.x — uses settings.yaml (not settings.yml).
#
# Prerequisites:
#   1. Native Ollama running: ollama serve (or already running as a service)
#   2. Models pulled:  ollama pull llama3.3:70b && ollama pull nomic-embed-text
#   3. Neo4j in Docker: docker compose up -d neo4j  (from on-prem/)
#   4. Python venv activated: source .venv/bin/activate
#   5. Corpus in on-prem/graphrag/input/  (symlink or real files)
#      Full corpus: cd on-prem/corpus && python seed_demo.py --no-llm
#                   then: ln -sfn ../corpus/silver input
#
# Usage (from on-prem/graphrag/):
#   bash scripts/ingest_native.sh
#
# Smoke-test mode (1 doc — confirm wiring before the full 38-doc bake):
#   mkdir -p input && cp ../corpus/hero/navigating-your-first-90-days.md input/
#   SMOKE=1 bash scripts/ingest_native.sh
#
# Security note: Ollama stays bound to 127.0.0.1. This script does NOT set
# OLLAMA_HOST=0.0.0.0 — native GraphRAG reaches Ollama on localhost directly.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GRAPHRAG_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Verify Ollama is reachable ───────────────────────────────────────────────
echo "[preflight] checking native Ollama at http://localhost:11434 ..."
if ! curl -sf http://localhost:11434/api/tags > /dev/null; then
  echo "ERROR: Ollama not reachable at http://localhost:11434."
  echo "  Start it with: ollama serve"
  exit 1
fi
echo "[preflight] Ollama OK"

# ── Verify Neo4j is reachable ────────────────────────────────────────────────
echo "[preflight] checking Neo4j at http://localhost:7474 ..."
if ! curl -sf http://localhost:7474 > /dev/null; then
  echo "ERROR: Neo4j not reachable at http://localhost:7474."
  echo "  Start it with: docker compose up -d neo4j  (from on-prem/)"
  exit 1
fi
echo "[preflight] Neo4j OK"

# ── Verify graphrag is installed ─────────────────────────────────────────────
if ! python -c "import graphrag" 2>/dev/null; then
  echo "ERROR: graphrag not importable. Activate your venv:"
  echo "  source .venv/bin/activate && pip install graphrag neo4j pandas pyarrow"
  exit 1
fi

# ── Point at native Ollama ────────────────────────────────────────────────────
export OLLAMA_BASE_URL="http://localhost:11434"
export GRAPHRAG_API_KEY="ollama"

# ── Resolve input and work root ───────────────────────────────────────────────
INPUT_DIR="${GRAPHRAG_ROOT}/input"
WORK_ROOT="${GRAPHRAG_ROOT}"

FIRST_AVAILABLE="$(find -L "${INPUT_DIR}" -maxdepth 1 \( -name "*.txt" -o -name "*.md" \) -print -quit)"
if [ ! -d "${INPUT_DIR}" ] || [ -z "${FIRST_AVAILABLE}" ]; then
  echo "ERROR: no .txt or .md files found in ${INPUT_DIR}"
  echo "  Smoke test: mkdir -p input && cp ../corpus/hero/navigating-your-first-90-days.md input/"
  echo "  Full bake:  ln -sfn ../corpus/silver input"
  exit 1
fi

if [ "${SMOKE:-0}" = "1" ]; then
  WORK_ROOT="${GRAPHRAG_ROOT}/.smoke_run"
  SMOKE_INPUT="${WORK_ROOT}/input"
  mkdir -p "${SMOKE_INPUT}"
  FIRST_DOC="$(find -L "${INPUT_DIR}" -maxdepth 1 \( -name "*.txt" -o -name "*.md" \) -print -quit)"
  cp "${FIRST_DOC}" "${SMOKE_INPUT}/"
  echo "[smoke] using 1 doc: $(basename "${FIRST_DOC}")"
fi

# ── Step 1: prepare workspace (no interactive init needed in 3.x) ─────────────
echo ""
echo "[1/3] Preparing GraphRAG 3.x workspace at ${WORK_ROOT} ..."
mkdir -p "${WORK_ROOT}/input" "${WORK_ROOT}/output" "${WORK_ROOT}/cache" "${WORK_ROOT}/logs"

# Copy our settings.yaml into the workspace root (skip if already there)
if [ "${WORK_ROOT}" != "${GRAPHRAG_ROOT}" ]; then
  cp "${GRAPHRAG_ROOT}/settings.yaml" "${WORK_ROOT}/settings.yaml"
fi

# Smoke path: copy one doc into .smoke_run/input/ (already done above).
# Full-bake path: input/ is already set up by the user (real dir or symlink to silver/).
# Nothing to do here — graphrag reads input/ from the workspace root directly.

echo "  settings.yaml copied, directories ready"

# ── Step 2: index ─────────────────────────────────────────────────────────────
echo ""
echo "[2/3] Running GraphRAG 3.x Full Standard index ..."
echo "      Monitor: tail -f ${WORK_ROOT}/logs/indexing-engine.log"
graphrag index --root "${WORK_ROOT}"

# ── Step 3: load into Neo4j ───────────────────────────────────────────────────
echo ""
echo "[3/3] Loading graph output into Neo4j at bolt://localhost:7687 ..."
NEO4J_URI="bolt://localhost:7687" \
NEO4J_USER="${NEO4J_USER:-neo4j}" \
NEO4J_PASSWORD="${NEO4J_PASSWORD:?NEO4J_PASSWORD must be set — source .env.local}" \
python "${SCRIPT_DIR}/load_neo4j.py" --output-dir "${WORK_ROOT}/output"

echo ""
echo "Done. Corpus indexed and loaded into Neo4j."
if [ "${SMOKE:-0}" = "1" ]; then
  echo "Smoke test passed. Full bake: ln -sfn ../corpus/silver input && bash scripts/ingest_native.sh"
fi
