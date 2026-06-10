import os

from neo4j import AsyncDriver, AsyncGraphDatabase

_NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
_NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
_NEO4J_PASSWORD = os.environ["NEO4J_PASSWORD"]

_driver: AsyncDriver | None = None


async def get_driver() -> AsyncDriver:
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(_NEO4J_URI, auth=(_NEO4J_USER, _NEO4J_PASSWORD))
    return _driver


async def close_driver() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


async def search_chunks(session, embedding: list[float], top_k: int) -> list[dict]:
    result = await session.run(
        """
        CALL db.index.vector.queryNodes('chunk_embedding', $top_k, $embedding)
        YIELD node AS chunk, score
        MATCH (chunk)-[:PART_OF]->(doc:Document)
        OPTIONAL MATCH (chunk)<-[:MENTIONED_IN]-(entity:Entity)
        RETURN chunk.id        AS chunk_id,
               chunk.text      AS text,
               score,
               doc.id          AS doc_id,
               doc.title       AS doc_title,
               collect(entity.name) AS entities
        ORDER BY score DESC
        """,
        top_k=top_k,
        embedding=embedding,
    )
    records = await result.data()
    return [
        {
            "chunk_id": r["chunk_id"],
            "text": r["text"],
            "score": r["score"],
            "doc_id": r["doc_id"],
            "doc_title": r.get("doc_title"),
            "entities": [e for e in (r["entities"] or []) if e],
        }
        for r in records
    ]


async def search_entities(
    session, embedding: list[float], top_k: int
) -> tuple[list[dict], list[dict]]:
    """GraphRAG local-search pattern: entity vector search + community context."""
    result = await session.run(
        """
        CALL db.index.vector.queryNodes('entity_embedding', $top_k, $embedding)
        YIELD node AS entity, score
        OPTIONAL MATCH (entity)-[:MEMBER_OF]->(community:Community)
        RETURN entity.name        AS name,
               entity.description AS description,
               entity.entity_type AS entity_type,
               score,
               collect(DISTINCT {
                   id:      community.id,
                   title:   community.title,
                   summary: community.summary,
                   level:   community.level
               }) AS communities
        ORDER BY score DESC
        """,
        top_k=top_k,
        embedding=embedding,
    )
    records = await result.data()

    entities: list[dict] = []
    seen_communities: set[str] = set()
    communities: list[dict] = []

    for r in records:
        entities.append(
            {
                "name": r["name"],
                "description": r.get("description"),
                "entity_type": r.get("entity_type"),
                "score": r["score"],
            }
        )
        for c in r.get("communities") or []:
            if c.get("id") and c["id"] not in seen_communities:
                seen_communities.add(c["id"])
                communities.append(
                    {
                        "community_id": c["id"],
                        "title": c.get("title"),
                        "summary": c.get("summary"),
                        "level": c.get("level"),
                    }
                )

    return entities, communities


async def persist_answer(
    session,
    answer_id: str,
    query: str,
    chunk_ids: list[str],
    community_ids: list[str],
) -> None:
    # Pass parameters as a dict — passing `query=` as a kwarg conflicts with
    # the neo4j 6.x driver's own `query` positional parameter name.
    await session.run(
        """
        CREATE (a:Answer {id: $answer_id, query: $query, created_at: datetime()})
        WITH a
        UNWIND $chunk_ids AS cid
        MATCH (c:Chunk {id: cid})
        CREATE (a)-[:USED]->(c)
        WITH a
        UNWIND $community_ids AS cmid
        MATCH (cm:Community {id: cmid})
        CREATE (a)-[:USED_COMMUNITY]->(cm)
        """,
        {
            "answer_id":    answer_id,
            "query":        query,
            "chunk_ids":    chunk_ids,
            "community_ids": community_ids,
        },
    )


async def traverse_entity(session, entity: str, depth: int) -> dict:
    # depth is validated as int 1–3 by the caller; inlining is safe
    result = await session.run(
        f"""
        MATCH (start:Entity)
        WHERE toLower(start.name) = toLower($entity)
        OPTIONAL MATCH path = (start)-[:RELATED_TO*1..{depth}]->(neighbor:Entity)
        WITH start,
             neighbor,
             [r IN relationships(path) | {{rel_type: r.rel_type, description: r.description}}]
               AS path_rels
        RETURN start.name           AS root,
               start.description    AS root_desc,
               neighbor.name        AS neighbor_name,
               neighbor.description AS neighbor_desc,
               path_rels
        LIMIT 50
        """,
        entity=entity,
    )
    records = await result.data()

    if not records:
        return {"root_entity": entity, "nodes": []}

    first = records[0]
    root_node = {
        "name": first["root"],
        "description": first.get("root_desc"),
        "relations": [
            {
                "neighbor": r["neighbor_name"],
                "rel_type": (r["path_rels"][-1] or {}).get("rel_type")
                if r.get("path_rels")
                else None,
                "description": (r["path_rels"][-1] or {}).get("description")
                if r.get("path_rels")
                else None,
            }
            for r in records
            if r.get("neighbor_name")
        ],
    }
    return {"root_entity": entity, "nodes": [root_node]}


async def resolve_onboarding_people(session, person: str) -> list[dict]:
    """ADR-025 typed onboarding traversal — resolve the named onboarding people for a
    new hire from the Person layer (Schema v2): manager, buddy, practice_lead,
    engagement_lead. Returns {name, role, relationship, why, scope} per resolved person.
    Empty list if the name isn't a Person (caller falls back to entity neighbourhood).
    """
    result = await session.run(
        """
        MATCH (p:Person) WHERE toLower(p.name) = toLower($person)
        OPTIONAL MATCH (p)-[:REPORTS_TO]->(mgr:Person)
        OPTIONAL MATCH (mgr)-[:HAS_ROLE]->(mgrRole:Role)
        OPTIONAL MATCH (p)-[:BUDDY_OF]->(bud:Person)
        OPTIONAL MATCH (bud)-[:HAS_ROLE]->(budRole:Role)
        OPTIONAL MATCH (p)-[:MEMBER_OF]->(pr:Practice)<-[:LEADS]-(pl:Person)
        OPTIONAL MATCH (pl)-[:HAS_ROLE]->(plRole:Role)
        OPTIONAL MATCH (p)-[:STAFFED_ON]->(e:Engagement)<-[:LEADS]-(el:Person)
        OPTIONAL MATCH (el)-[:HAS_ROLE]->(elRole:Role)
        RETURN p.name                         AS root,
               mgr.name                       AS manager,        mgrRole.title AS manager_role,
               bud.name                       AS buddy,          budRole.title AS buddy_role,
               pr.name                        AS practice,
               pl.name                        AS practice_lead,  plRole.title  AS practice_lead_role,
               coalesce(e.client, e.name, e.id) AS engagement,
               el.name                        AS engagement_lead, elRole.title AS engagement_lead_role
        LIMIT 1
        """,
        person=person,
    )
    r = await result.single()
    if not r or not r["root"]:
        return []

    people: list[dict] = []
    if r["manager"]:
        people.append({
            "name": r["manager"], "role": r.get("manager_role"),
            "relationship": "manager", "scope": "reporting line",
            "why": "Your manager — align on goals and what success looks like in your first 30 days.",
        })
    if r["buddy"]:
        people.append({
            "name": r["buddy"], "role": r.get("buddy_role"),
            "relationship": "buddy", "scope": "onboarding",
            "why": "Your assigned onboarding buddy — the person to ask the 'obvious' questions first.",
        })
    if r["practice_lead"]:
        people.append({
            "name": r["practice_lead"], "role": r.get("practice_lead_role"),
            "relationship": "practice_lead", "scope": r.get("practice"),
            "why": f"Leads the {r.get('practice')} practice you're a member of.",
        })
    if r["engagement_lead"]:
        people.append({
            "name": r["engagement_lead"], "role": r.get("engagement_lead_role"),
            "relationship": "engagement_lead", "scope": r.get("engagement"),
            "why": f"Leads {r.get('engagement')}, the engagement you're staffed on — routes access and client context.",
        })
    return people


async def path_between(session, a: str, b: str) -> dict:
    """ADR-025 path_between mode — the relationship path between two entities = the
    'why should I meet X' narrative. Matches nodes by name/client/title/id across labels,
    shortest undirected path up to 5 hops."""
    # Prefer the structured Schema-v2 layer (Person/Engagement/Practice/Team/Role/…) over
    # the fuzzy GraphRAG Entity layer, so the path reads as a real org relationship rather
    # than a co-mention. Fall back to any-label match if the structured layer has no path.
    structured = """
        MATCH (a) WHERE toLower(coalesce(a.name, a.client, a.title, a.id, '')) = toLower($a)
              AND NOT a:Entity AND NOT a:Chunk AND NOT a:Community AND NOT a:Document
        MATCH (b) WHERE toLower(coalesce(b.name, b.client, b.title, b.id, '')) = toLower($b)
              AND NOT b:Entity AND NOT b:Chunk AND NOT b:Community AND NOT b:Document
        MATCH path = shortestPath((a)-[*..5]-(b))
        RETURN [n IN nodes(path) | coalesce(n.name, n.client, n.title, n.id)] AS node_names,
               [r IN relationships(path) | type(r)]                          AS rel_types
        LIMIT 1
    """
    permissive = """
        MATCH (a) WHERE toLower(coalesce(a.name, a.client, a.title, a.id, '')) = toLower($a)
        MATCH (b) WHERE toLower(coalesce(b.name, b.client, b.title, b.id, '')) = toLower($b)
        MATCH path = shortestPath((a)-[*..5]-(b))
        RETURN [n IN nodes(path) | coalesce(n.name, n.client, n.title, n.id)] AS node_names,
               [r IN relationships(path) | type(r)]                          AS rel_types
        LIMIT 1
    """
    r = await (await session.run(structured, {"a": a, "b": b})).single()
    if not r or not r["node_names"]:
        r = await (await session.run(permissive, {"a": a, "b": b})).single()
    if not r or not r["node_names"]:
        return {"a": a, "b": b, "path": [], "narrative": f"No relationship path found between {a} and {b} within 5 hops."}

    names = r["node_names"]
    rels  = r["rel_types"]
    hops = [{"from": names[i], "rel": rels[i], "to": names[i + 1]} for i in range(len(rels))]
    # Human narrative: "A —REPORTS_TO→ B —LEADS← C"
    narrative_parts = [names[0]]
    for i, rel in enumerate(rels):
        narrative_parts.append(f"—[{rel}]—")
        narrative_parts.append(names[i + 1])
    return {"a": a, "b": b, "path": hops, "narrative": " ".join(narrative_parts)}


async def explain_answer(session, answer_id: str) -> dict:
    result = await session.run(
        """
        MATCH (a:Answer {id: $answer_id})
        OPTIONAL MATCH (a)-[:USED]->(chunk:Chunk)-[:PART_OF]->(doc:Document)
        OPTIONAL MATCH (chunk)<-[:MENTIONED_IN]-(entity:Entity)
        OPTIONAL MATCH (a)-[:USED_COMMUNITY]->(community:Community)
        RETURN a.query                             AS query,
               collect(DISTINCT chunk.id)          AS chunk_ids,
               collect(DISTINCT entity.name)       AS entities,
               collect(DISTINCT doc.title)         AS doc_titles,
               collect(DISTINCT community.title)   AS community_titles
        """,
        answer_id=answer_id,
    )
    record = await result.single()

    if not record or record["query"] is None:
        raise ValueError(f"Answer not found: {answer_id}")

    return {
        "answer_id": answer_id,
        "query": record["query"],
        "chunks_used": record["chunk_ids"] or [],
        "entities_involved": [e for e in (record["entities"] or []) if e],
        "documents_sourced": [d for d in (record["doc_titles"] or []) if d],
        "communities_used": [c for c in (record["community_titles"] or []) if c],
    }
