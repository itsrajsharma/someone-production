CREATE TABLE IF NOT EXISTS relationship_state (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    persona TEXT NOT NULL DEFAULT 'aria',
    intimacy_depth DOUBLE PRECISION NOT NULL DEFAULT 0.1,
    relationship_momentum TEXT NOT NULL DEFAULT 'stable',
    inside_references JSONB NOT NULL DEFAULT '[]'::jsonb,
    tender_topics JSONB NOT NULL DEFAULT '[]'::jsonb,
    established_patterns JSONB NOT NULL DEFAULT '[]'::jsonb,
    relationship_defining_moments JSONB NOT NULL DEFAULT '[]'::jsonb,
    what_aria_is_carrying JSONB NOT NULL DEFAULT '[]'::jsonb,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, persona)
);
