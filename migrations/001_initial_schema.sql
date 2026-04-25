-- ============================================================
-- Someone v1 — Phase 1 Database Migration
-- Run this in Supabase SQL Editor
-- ============================================================

-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- ─────────────────────────────────────────────────────────────
-- TURNS  (replaces turns.json + oracle_turns.json)
-- persona = 'aria' | 'oracle'
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS turns (
    pk          BIGSERIAL PRIMARY KEY,
    id          TEXT NOT NULL,                -- 8-char uuid slice from pipeline
    user_id     UUID NOT NULL,
    persona     TEXT NOT NULL DEFAULT 'aria',
    role        TEXT NOT NULL,                -- 'user' | 'assistant'
    content     TEXT NOT NULL,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    causal_tags JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_turns_user_persona  ON turns (user_id, persona);
CREATE INDEX IF NOT EXISTS idx_turns_user_ts       ON turns (user_id, persona, timestamp);

-- ─────────────────────────────────────────────────────────────
-- SESSION FACTS  (replaces in-memory _session_facts list)
-- Cleared per session (session_id = UUID generated at login)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS session_facts (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID NOT NULL,
    session_id  UUID NOT NULL,
    persona     TEXT NOT NULL DEFAULT 'aria',
    fact        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_session_facts_lookup ON session_facts (user_id, session_id, persona);

-- ─────────────────────────────────────────────────────────────
-- EBF  (replaces ebf.json — one row per user+persona, upserted)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ebf (
    id                        BIGSERIAL PRIMARY KEY,
    user_id                   UUID NOT NULL,
    persona                   TEXT NOT NULL DEFAULT 'aria',
    dominant_emotion_pattern  TEXT NOT NULL DEFAULT 'unknown',
    communication_style       TEXT NOT NULL DEFAULT 'neutral',
    trust_level               DOUBLE PRECISION NOT NULL DEFAULT 0.10,
    current_state             TEXT NOT NULL DEFAULT 'neutral',
    unmet_need                TEXT NOT NULL DEFAULT '',
    response_preference       TEXT NOT NULL DEFAULT 'balanced',
    session_message_count     INTEGER NOT NULL DEFAULT 0,
    total_message_count       INTEGER NOT NULL DEFAULT 0,
    energy_level              TEXT NOT NULL DEFAULT 'medium',
    last_updated              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, persona)
);

-- ─────────────────────────────────────────────────────────────
-- SNAPSHOTS  (replaces snapshots.json)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS snapshots (
    id                       BIGSERIAL PRIMARY KEY,
    user_id                  UUID NOT NULL,
    persona                  TEXT NOT NULL DEFAULT 'aria',
    date                     DATE NOT NULL,
    time_of_day              TEXT NOT NULL,
    facts_learned            JSONB NOT NULL DEFAULT '[]'::jsonb,
    emotional_tone           TEXT NOT NULL DEFAULT 'neutral',
    energy_level             TEXT NOT NULL DEFAULT 'medium',
    events                   JSONB NOT NULL DEFAULT '[]'::jsonb,
    open_stories             JSONB NOT NULL DEFAULT '[]'::jsonb,
    behaviour_signal         TEXT NOT NULL DEFAULT '',
    communication_style      TEXT NOT NULL DEFAULT 'neutral',
    trust_level_at_snapshot  DOUBLE PRECISION NOT NULL DEFAULT 0.1,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_snapshots_user_persona ON snapshots (user_id, persona, created_at);

-- ─────────────────────────────────────────────────────────────
-- OPEN STORIES  (replaces open_stories.json)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS open_stories (
    id          BIGSERIAL PRIMARY KEY,
    story_id    TEXT NOT NULL,               -- 'story_xxxxxx' slug
    user_id     UUID NOT NULL,
    persona     TEXT NOT NULL DEFAULT 'aria',
    title       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open', -- 'open' | 'resolved'
    first_told  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_told   TIMESTAMPTZ NOT NULL DEFAULT now(),
    summary     TEXT NOT NULL DEFAULT '',
    resolved_at TIMESTAMPTZ,
    UNIQUE (story_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_open_stories_user_persona ON open_stories (user_id, persona, status);

-- ─────────────────────────────────────────────────────────────
-- TENSIONS  (replaces tensions.json)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tensions (
    id          BIGSERIAL PRIMARY KEY,
    tension_id  TEXT NOT NULL,               -- 8-char uuid slice
    user_id     UUID NOT NULL,
    persona     TEXT NOT NULL DEFAULT 'aria',
    type        TEXT NOT NULL,               -- 'open_question' | 'stated_goal' | 'deflected_emotion'
    summary     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open', -- 'open' | 'resolved'
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    UNIQUE (tension_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_tensions_user_persona ON tensions (user_id, persona, status);

-- ─────────────────────────────────────────────────────────────
-- BEHAVIOUR RHYTHM  (replaces rhythm.json)
-- One row per user+persona, upserted
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS behaviour_rhythm (
    id                       BIGSERIAL PRIMARY KEY,
    user_id                  UUID NOT NULL,
    persona                  TEXT NOT NULL DEFAULT 'aria',
    most_open_time           TEXT NOT NULL DEFAULT 'unknown',
    most_stressed_day        TEXT NOT NULL DEFAULT 'unknown',
    storytelling_frequency   TEXT NOT NULL DEFAULT 'unknown',
    trust_growth_rate        TEXT NOT NULL DEFAULT 'unknown',
    session_times            JSONB NOT NULL DEFAULT '[]'::jsonb,
    snapshot_count           INTEGER NOT NULL DEFAULT 0,
    last_updated             TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, persona)
);

-- ─────────────────────────────────────────────────────────────
-- CORE IDENTITY  (replaces core_identity.json)
-- One row per user, upserted (non-persona-specific)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core_identity (
    id                             BIGSERIAL PRIMARY KEY,
    user_id                        UUID NOT NULL UNIQUE,
    snapshot_count_at_last_update  INTEGER NOT NULL DEFAULT 0,
    psychological_profile          TEXT NOT NULL DEFAULT 'No profile exists yet.',
    current_life_chapter           TEXT NOT NULL DEFAULT 'Unknown.',
    enduring_traits                JSONB NOT NULL DEFAULT '[]'::jsonb,
    last_updated                   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─────────────────────────────────────────────────────────────
-- HEALTH REPORTS  (replaces health_report.json)
-- Append-only; scaffold reads the latest row for user
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS health_reports (
    id                    BIGSERIAL PRIMARY KEY,
    user_id               UUID NOT NULL,
    week_summary          JSONB NOT NULL DEFAULT '{}'::jsonb,
    anomalies             JSONB NOT NULL DEFAULT '[]'::jsonb,
    compared_to_last_week JSONB,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_health_reports_user ON health_reports (user_id, created_at DESC);

-- ─────────────────────────────────────────────────────────────
-- TURN EMBEDDINGS  (replaces ChromaDB aria_turns collection)
-- vector(1024) for Mistral Embed API (mistral-embed)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS turn_embeddings (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID NOT NULL,
    persona     TEXT NOT NULL DEFAULT 'aria',
    turn_pk     BIGINT NOT NULL REFERENCES turns(pk) ON DELETE CASCADE,
    turn_id     TEXT NOT NULL,               -- mirrors turns.id
    content     TEXT NOT NULL,
    embedding   vector(1024) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (turn_id, user_id)
);

-- IVFFlat index for fast ANN search (cosine distance)
-- Re-run after you have > 1000 rows for best performance:
-- CREATE INDEX turn_embeddings_ivfflat ON turn_embeddings
--   USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- For now use exact cosine search (fine under ~10k rows):
CREATE INDEX IF NOT EXISTS idx_turn_embeddings_user_persona ON turn_embeddings (user_id, persona);
