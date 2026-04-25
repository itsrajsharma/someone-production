"""
db/client.py — Supabase client singleton.
Import get_db() anywhere you need a database handle.
"""

import os
from supabase import create_client, Client

_client: Client | None = None


def get_db() -> Client:
    """Return a Supabase client, initialising it on first call."""
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_KEY", "").strip()
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_KEY must be set in the environment."
            )
        _client = create_client(url, key)
    return _client
