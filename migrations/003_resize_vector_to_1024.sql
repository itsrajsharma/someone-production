-- ============================================================
-- Someone v1 — Phase 2 DB Migration (Mistral API)
-- Run this in Supabase SQL Editor to swap 384d to 1024d
-- ============================================================

-- 1. Truncate existing turn_embeddings (will auto-regenerate on next prompt)
TRUNCATE TABLE turn_embeddings;

-- 2. Alter the column type to 1024 dimensions
ALTER TABLE turn_embeddings ALTER COLUMN embedding TYPE vector(1024);

-- 3. Drop the old RPC (signature uses vector(384))
DROP FUNCTION IF EXISTS match_turn_embeddings(vector(384), uuid, text, int);
DROP FUNCTION IF EXISTS match_turn_embeddings(vector, uuid, text, int);

-- 4. Recreate the RPC with vector(1024)
CREATE OR REPLACE FUNCTION match_turn_embeddings(
    query_embedding  vector(1024),
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
