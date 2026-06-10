#!/usr/bin/env python3
"""
Load GraphRAG 3.x full-pipeline parquet output into Neo4j.

GraphRAG 3.x writes Parquet files directly under output/:
  - documents.parquet
  - text_units.parquet        (chunks; embeddings are in LanceDB, not here)
  - entities.parquet          (uses 'title' not 'name'; no description_embedding)
  - relationships.parquet
  - communities.parquet       (Leiden community structure)
  - community_reports.parquet (LLM-written community summaries)

This script reads those files and upserts them into the Neo4j schema
defined in on-prem/neo4j/init/01_schema.cypher.
"""
import argparse
import os
from pathlib import Path

import pandas as pd
from neo4j import GraphDatabase

NEO4J_URI = os.environ["NEO4J_URI"]
NEO4J_USER = os.environ["NEO4J_USER"]
NEO4J_PASSWORD = os.environ["NEO4J_PASSWORD"]

# Default is the Docker container path; override with --output-dir for native runs.
# GraphRAG 3.x: parquet files are directly in output/ (no artifacts/ subfolder).
_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--output-dir", default="/app/output")
_args, _ = _parser.parse_known_args()
ARTIFACTS = Path(_args.output_dir)

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def load_documents(session):
    path = ARTIFACTS / "documents.parquet"
    if not path.exists():
        print(f"  skip: {path.name} not found")
        return
    df = pd.read_parquet(path)[["id", "title"]].fillna("")
    records = df.to_dict("records")
    session.run(
        "UNWIND $rows AS row MERGE (d:Document {id: row.id}) SET d.title = row.title",
        rows=records,
    )
    print(f"  loaded {len(records)} documents")


def load_chunks(session):
    path = ARTIFACTS / "text_units.parquet"
    if not path.exists():
        print(f"  skip: {path.name} not found")
        return
    df = pd.read_parquet(path)
    records = []
    for _, row in df.iterrows():
        records.append({
            "id":     str(row["id"]),
            "text":   str(row.get("text", "")),
            "doc_id": str(row["document_id"]) if pd.notna(row.get("document_id")) else None,
        })
    session.run(
        """UNWIND $rows AS row
           MERGE (c:Chunk {id: row.id})
           SET c.text = row.text
           WITH c, row WHERE row.doc_id IS NOT NULL
           MATCH (d:Document {id: row.doc_id})
           MERGE (c)-[:PART_OF]->(d)""",
        rows=records,
    )
    print(f"  loaded {len(records)} chunks")


def load_entities(session):
    path = ARTIFACTS / "entities.parquet"
    if not path.exists():
        print(f"  skip: {path.name} not found")
        return
    df = pd.read_parquet(path)
    records = []
    for _, row in df.iterrows():
        records.append({
            "id":          str(row["id"]),
            "name":        str(row.get("title", "")),   # 3.x uses 'title' not 'name'
            "type":        str(row.get("type", "")),
            "description": str(row.get("description", "")),
            "chunk_ids":   [str(x) for x in (row["text_unit_ids"] if row.get("text_unit_ids") is not None else [])],
        })
    session.run(
        """UNWIND $rows AS row
           MERGE (e:Entity {id: row.id})
           SET e.name = row.name,
               e.entity_type = row.type,
               e.description = row.description""",
        rows=records,
    )
    # Wire MENTIONED_IN edges separately
    session.run(
        """UNWIND $rows AS row
           MATCH (e:Entity {id: row.id})
           UNWIND row.chunk_ids AS cid
           MATCH (c:Chunk {id: cid})
           MERGE (e)-[:MENTIONED_IN]->(c)""",
        rows=records,
    )
    print(f"  loaded {len(records)} entities")


def load_relationships(session):
    path = ARTIFACTS / "relationships.parquet"
    if not path.exists():
        print(f"  skip: {path.name} not found")
        return
    df = pd.read_parquet(path)[["source", "target", "description", "weight"]].fillna("")
    records = df.to_dict("records")
    session.run(
        """UNWIND $rows AS row
           MATCH (src:Entity {name: row.source})
           MATCH (tgt:Entity {name: row.target})
           MERGE (src)-[r:RELATED_TO]->(tgt)
           SET r.description = row.description,
               r.weight = toFloat(row.weight)""",
        rows=records,
    )
    print(f"  loaded {len(records)} relationships")


def load_communities(session):
    path = ARTIFACTS / "communities.parquet"
    if not path.exists():
        print(f"  skip: {path.name} not found")
        return
    df = pd.read_parquet(path)
    records = []
    for _, row in df.iterrows():
        records.append({
            "id":         str(row["id"]),
            "title":      str(row.get("title", "")),
            "level":      int(row.get("level", 0)),
            "entity_ids": [str(x) for x in (row["entity_ids"] if row.get("entity_ids") is not None else [])],
        })
    session.run(
        """UNWIND $rows AS row
           MERGE (cm:Community {id: row.id})
           SET cm.title = row.title, cm.level = row.level""",
        rows=records,
    )
    session.run(
        """UNWIND $rows AS row
           MATCH (cm:Community {id: row.id})
           UNWIND row.entity_ids AS eid
           MATCH (e:Entity {id: eid})
           MERGE (e)-[:MEMBER_OF]->(cm)""",
        rows=records,
    )
    print(f"  loaded {len(records)} communities")


def load_community_reports(session):
    path = ARTIFACTS / "community_reports.parquet"
    if not path.exists():
        print(f"  skip: {path.name} not found")
        return
    df = pd.read_parquet(path)
    records = []
    for _, row in df.iterrows():
        records.append({
            "community_id": str(row.get("community", row.get("id", ""))),
            "summary":      str(row.get("full_content", row.get("summary", ""))),
            "rank":         float(row.get("rank", 0.0)),
        })
    session.run(
        """UNWIND $rows AS row
           MATCH (cm:Community {id: row.community_id})
           SET cm.summary = row.summary, cm.rank = row.rank""",
        rows=records,
    )
    print(f"  loaded {len(records)} community reports")


def main():
    print("Loading GraphRAG 3.x artifacts into Neo4j...")
    with driver.session() as session:
        load_documents(session)
        load_chunks(session)
        load_entities(session)
        load_relationships(session)
        load_communities(session)
        load_community_reports(session)
    driver.close()
    print("Load complete.")


if __name__ == "__main__":
    main()
