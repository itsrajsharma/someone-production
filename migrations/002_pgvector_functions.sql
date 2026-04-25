-- ============================================================
-- Someone v1 — Supabase Helper Functions
-- Run AFTER 001_initial_schema.sql
-- ============================================================

-- pgvector cosine similarity search function
-- Called by dependency_resolver.py as db.rpc("match_turn_embeddings", {...})
CREATE OR REPLACE FUNCTION match_turn_embeddings(
    query_embedding  vector(384),
    match_user_id    uuid,
    match_persona    text,
    match_count      int DEFAULT 6
)
RETURNS TABLE (
    turn_id    text,
    content    text,
    similarity double precision
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        te.turn_id,
        te.content,
        1 - (te.embedding <=> query_embedding) AS similarity
    FROM turn_embeddings te
    WHERE te.user_id = match_user_id
      AND te.persona = match_persona
    ORDER BY te.embedding <=> query_embedding  -- cosine distance (ascending)
    LIMIT match_count;
END;
$$;
