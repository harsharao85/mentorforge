# MentorForge — On-Prem Stack

Docker Compose services for the on-prem component of the MentorForge hybrid architecture (ADR-001): Neo4j, Ollama, GraphRAG indexer, and FastAPI MCP server.

## Two run profiles

| Profile | Ollama | GraphRAG | Neo4j | When |
|---|---|---|---|---|
| **`linux`** (prod / customer VM) | container (`ollama/ollama:0.5.13`) with GPU passthrough | container (`graphrag-indexer`) | container | Linux VM with NVIDIA GPU |
| **`mac`** (Apple Silicon demo host) | **native (Metal, `llama3.3:70b` already pulled)** | **native venv** | container | Harsha's M2 Ultra |

Both profiles use the same `settings.yml` and `load_neo4j.py`. The difference is where Ollama and GraphRAG run — never fork the config.

---

## Mac quickstart (M2 Ultra / Apple Silicon)

On Apple Silicon, containerized Ollama cannot access Metal — CPU-only inference makes a 70B Full Standard bake take days. Run Ollama natively and GraphRAG in a venv instead.

### Prerequisites

- Docker Desktop running
- Ollama installed natively (`brew install ollama`) with models already pulled:
  ```bash
  ollama pull llama3.3:70b
  ollama pull nomic-embed-text
  ```
- Python 3.11+ for the graphrag venv

### Step 1 — Start Neo4j (Docker only)

```bash
cd on-prem
cp .env.example .env.local    # first time only — set NEO4J_PASSWORD + MCP_BEARER_TOKEN
source .env.local             # or export NEO4J_PASSWORD=... manually

docker compose up -d neo4j
docker compose up neo4j-init  # one-shot schema init — exits when done
```

Verify: `curl -s http://localhost:7474` returns Neo4j browser HTML.

> **mcp_server on Mac:** The MCP server runs in Docker but must reach native Ollama. Before `docker compose up mcp_server`, set:
> ```bash
> export OLLAMA_BASE_URL=http://host.docker.internal:11434
> ```
> The compose file defaults to `http://ollama:11434` (Linux container DNS) — override it for Mac.

### Step 2 — Set up the GraphRAG venv

```bash
cd on-prem/graphrag
python3 -m venv .venv
source .venv/bin/activate
pip install graphrag neo4j pandas pyarrow
```

### Step 3 — Assemble the corpus

```bash
cd on-prem/corpus
source ../.env.local          # for NEO4J_PASSWORD
pip install -r requirements.txt
python patch_cast.py          # inject cast into datagen CSVs
python seed_demo.py           # assemble silver/ (38 docs with ADR-019 envelopes)
```

This writes `on-prem/corpus/silver/` — the GraphRAG input directory.

### Step 4 — Smoke test (1 doc — confirm wiring before the full bake)

```bash
cd on-prem/graphrag
source .venv/bin/activate
source ../.env.local

# Link corpus into GraphRAG input dir
ln -sfn ../corpus/silver input

SMOKE=1 bash scripts/ingest_native.sh
```

Expected: GraphRAG indexes 1 doc, loads it into Neo4j, exits cleanly. Check Neo4j browser at `http://localhost:7474` — you should see `Document`, `Chunk`, and `Entity` nodes.

### Step 5 — Full bake (38 docs)

```bash
cd on-prem/graphrag
source .venv/bin/activate
source ../.env.local

bash scripts/ingest_native.sh
```

A Full Standard bake of 38 docs with Llama 3.3 70B takes ~2–4 hours on M2 Ultra (Metal). Monitor:

```bash
tail -f on-prem/graphrag/logs/indexing-engine.log
```

### Step 6 — Load org graph

After the corpus bake, load the TASK-001 org graph into Neo4j:

```bash
cd on-prem/datagen
pip install -r requirements.txt
python generate.py            # if not already done — outputs output/
cypher-shell -u neo4j -p $NEO4J_PASSWORD < output/load.cypher
```

### Step 7 — Validate (EX story queries)

See `on-prem/corpus/README.md` §Story validation queries for Cypher to confirm Story 1–3 resolve correctly.

---

## Linux quickstart (VM with NVIDIA GPU)

All services run in Docker. GPU passthrough for Ollama requires the NVIDIA Container Toolkit.

```bash
cd on-prem
cp .env.example .env.local
source .env.local

# Start everything (Neo4j + Ollama + mcp_server)
docker compose --profile linux up -d

# Wait for Ollama to pull models (one-time, ~40 GB)
docker compose --profile linux logs -f ollama-init

# Once models are pulled, run the GraphRAG indexer
# (assemble corpus first — see on-prem/corpus/README.md)
ln -sfn $(pwd)/corpus/silver $(pwd)/graphrag/input

docker compose --profile linux --profile indexer run --rm graphrag-indexer
```

---

## Environment variables

| Variable | Required | Default | Notes |
|---|---|---|---|
| `NEO4J_PASSWORD` | ✅ | — | Set in `.env.local` |
| `MCP_BEARER_TOKEN` | ✅ | — | `openssl rand -hex 32` |
| `OLLAMA_BASE_URL` | Mac only | `http://ollama:11434` | Set to `http://host.docker.internal:11434` for Mac mcp_server |

> **Security:** Ollama must stay bound to `127.0.0.1` (its default). Do NOT set `OLLAMA_HOST=0.0.0.0`. The native GraphRAG venv reaches Ollama on localhost directly — no firewall change, no network exposure.

---

## Service ports (all localhost-only)

| Service | Port | Protocol |
|---|---|---|
| Neo4j Browser | 7474 | HTTP |
| Neo4j Bolt | 7687 | Bolt |
| Ollama (Linux/container) | 11434 | HTTP |
| MCP Server | 8443 | HTTPS |
