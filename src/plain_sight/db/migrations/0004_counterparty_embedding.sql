-- Counterparty embeddings for query-time semantic similarity (pgvector).
--
-- Gives every provisional counterparty an optional embedding vector so
-- "find declarations related to company X" can be served by ranking interests by
-- how near their counterparty sits to a query vector, computed *at query time*.
-- There is deliberately NO materialised cluster entity and no clustering
-- pipeline: clustering is unstable and edges toward Type-B inference. The stable
-- counterparty UUID is unchanged; the embedding is an additive retrieval aid, not
-- a resolved legal identity. Applies on top of 0003.
--
-- Vectors are for retrieval and entity-assist, never generation: similarity
-- surfaces cited records, it never asserts an ACN or any legal identity.

CREATE EXTENSION IF NOT EXISTS vector;

-- Nullable: a counterparty may exist before it has been embedded, and the
-- similarity query simply ignores rows whose embedding is still NULL. The
-- dimension must match plain_sight.db.postgres.EMBEDDING_DIMENSIONS.
ALTER TABLE counterparty
    ADD COLUMN embedding vector(1536);

-- HNSW over cosine distance (`<=>`): builds incrementally (no training step, so
-- it works on a small or initially-empty table) and indexes the exact operator
-- the similarity query orders by. Cosine matches the query-time distance metric.
CREATE INDEX counterparty_embedding_cosine_idx
    ON counterparty USING hnsw (embedding vector_cosine_ops);
