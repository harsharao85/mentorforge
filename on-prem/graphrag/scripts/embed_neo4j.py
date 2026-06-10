#!/usr/bin/env python3
"""
Generate and store embeddings for Chunk and Entity nodes in Neo4j.

GraphRAG's load_neo4j.py stores graph structure but not embeddings.
This script fills the gap: embeds each node's text via Ollama
(nomic-embed-text, 768-dim) and writes the vector back to Neo4j so the
chunk_embedding and entity_embedding vector indexes are populated.

Usage (from on-prem/graphrag/):
    NEO4J_URI=bolt://localhost:7687 NEO4J_USER=neo4j NEO4J_PASSWORD=<pw> \
        python3 scripts/embed_neo4j.py

Env vars (all required):
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
    OLLAMA_URL   — default http://localhost:11434
    EMBED_MODEL  — default nomic-embed-text
"""
import os
import sys
import time

import httpx
from neo4j import GraphDatabase

NEO4J_URI      = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER     = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ["NEO4J_PASSWORD"]
OLLAMA_URL     = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL    = os.environ.get("EMBED_MODEL", "nomic-embed-text")
BATCH_SIZE     = int(os.environ.get("BATCH_SIZE", "20"))


def embed(texts: list[str]) -> list[list[float]]:
    """Call Ollama embed endpoint for a batch of texts."""
    resp = httpx.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": EMBED_MODEL, "input": texts},
        timeout=120.0,
    )
    resp.raise_for_status()
    return resp.json()["embeddings"]


def embed_chunks(session) -> int:
    result = session.run("MATCH (c:Chunk) WHERE c.embedding IS NULL AND c.text IS NOT NULL RETURN c.id AS id, c.text AS text")
    rows = [(r["id"], r["text"]) for r in result]
    if not rows:
        print("  all chunks already embedded")
        return 0

    print(f"  embedding {len(rows)} chunks in batches of {BATCH_SIZE}…")
    done = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        ids   = [r[0] for r in batch]
        texts = [r[1] for r in batch]
        vecs  = embed(texts)
        session.run(
            "UNWIND $rows AS row MATCH (c:Chunk {id: row.id}) SET c.embedding = row.vec",
            rows=[{"id": id_, "vec": vec} for id_, vec in zip(ids, vecs)],
        )
        done += len(batch)
        print(f"    chunks {done}/{len(rows)}", end="\r", flush=True)
    print()
    return len(rows)


def embed_entities(session) -> int:
    result = session.run(
        "MATCH (e:Entity) WHERE e.embedding IS NULL AND e.description IS NOT NULL RETURN e.name AS name, e.description AS desc"
    )
    rows = [(r["name"], r["desc"]) for r in result]
    if not rows:
        print("  all entities already embedded")
        return 0

    print(f"  embedding {len(rows)} entities in batches of {BATCH_SIZE}…")
    done = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        names = [r[0] for r in batch]
        descs = [r[1] for r in batch]
        vecs  = embed(descs)
        session.run(
            "UNWIND $rows AS row MATCH (e:Entity {name: row.name}) SET e.embedding = row.vec",
            rows=[{"name": n, "vec": v} for n, v in zip(names, vecs)],
        )
        done += len(batch)
        print(f"    entities {done}/{len(rows)}", end="\r", flush=True)
    print()
    return len(rows)


def main():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    t0 = time.time()
    with driver.session() as session:
        print("=== Chunks ===")
        nc = embed_chunks(session)
        print("=== Entities ===")
        ne = embed_entities(session)
    driver.close()
    elapsed = time.time() - t0
    print(f"\nDone — {nc} chunks + {ne} entities embedded in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
