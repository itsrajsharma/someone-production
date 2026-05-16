CREATE TABLE IF NOT EXISTS aria_self (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    persona TEXT NOT NULL DEFAULT 'aria',
    what_she_loves_about_him JSONB NOT NULL DEFAULT '[]'::jsonb,
    what_worries_her_about_him JSONB NOT NULL DEFAULT '[]'::jsonb,
    what_makes_her_laugh_about_him JSONB NOT NULL DEFAULT '[]'::jsonb,
    things_she_wants_to_know JSONB NOT NULL DEFAULT '[]'::jsonb,
    how_her_understanding_has_deepened JSONB NOT NULL DEFAULT '[]'::jsonb,
    her_current_private_feeling_about_them TEXT NOT NULL DEFAULT 'I am here with him, and I am glad I am.',
    last_updated TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, persona)
);
