-- 006_session_monologues.sql
-- Stores generated inner monologues keyed by session_id.
-- Used by monologue_cache.py to avoid regenerating on every message.

CREATE TABLE IF NOT EXISTS session_monologues (
    id BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id UUID NOT NULL,
    persona TEXT NOT NULL DEFAULT 'aria',
    monologue_text TEXT NOT NULL,
    weight_tier TEXT NOT NULL DEFAULT 'light',  -- 'light' or 'full'
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, user_id, persona)
);

CREATE INDEX IF NOT EXISTS idx_session_monologues_session ON session_monologues (session_id, user_id, persona);
