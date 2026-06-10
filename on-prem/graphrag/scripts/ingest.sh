#!/bin/bash
# Indexes documents from /app/input and loads the resulting knowledge graph into Neo4j.
# Invoked by: docker compose --profile indexer run --rm graphrag-indexer
set -euo pipefail

echo "[1/3] Initializing GraphRAG workspace..."
graphrag init --root /app --force

echo "[2/3] Running GraphRAG index pipeline (this can take a while for large corpora)..."
graphrag index --root /app

echo "[3/3] Loading graph output into Neo4j..."
python /app/scripts/load_neo4j.py

echo "Done. Corpus indexed and loaded into Neo4j."
