// ============================================================
// MentorForge — Neo4j schema for GraphRAG knowledge graph
// Run once at init; idempotent (IF NOT EXISTS guards).
// ============================================================

// --- Uniqueness constraints ---
CREATE CONSTRAINT document_id IF NOT EXISTS
  FOR (d:Document) REQUIRE d.id IS UNIQUE;

CREATE CONSTRAINT chunk_id IF NOT EXISTS
  FOR (c:Chunk) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT entity_id IF NOT EXISTS
  FOR (e:Entity) REQUIRE e.id IS UNIQUE;

CREATE CONSTRAINT community_id IF NOT EXISTS
  FOR (cm:Community) REQUIRE cm.id IS UNIQUE;

CREATE CONSTRAINT answer_id IF NOT EXISTS
  FOR (a:Answer) REQUIRE a.id IS UNIQUE;

// --- Vector indexes (nomic-embed-text = 768 dims, cosine similarity) ---
CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS
  FOR (c:Chunk) ON (c.embedding)
  OPTIONS {indexConfig: {`vector.dimensions`: 768, `vector.similarity_function`: 'cosine'}};

CREATE VECTOR INDEX entity_embedding IF NOT EXISTS
  FOR (e:Entity) ON (e.embedding)
  OPTIONS {indexConfig: {`vector.dimensions`: 768, `vector.similarity_function`: 'cosine'}};

// --- Full-text index for keyword search fallback ---
CREATE FULLTEXT INDEX chunk_text IF NOT EXISTS
  FOR (n:Chunk) ON EACH [n.text];

CREATE FULLTEXT INDEX entity_name IF NOT EXISTS
  FOR (n:Entity) ON EACH [n.name, n.description];
