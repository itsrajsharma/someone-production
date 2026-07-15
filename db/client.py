"""
db/client.py — Supabase client singleton.
Import get_db() anywhere you need a database handle.
"""

import os
from supabase import create_client, Client

_client: Client | None = None


def get_db() -> Client:
    """
    Return a Supabase client singleton for general DB queries.
    Uses the service_role key to run as a trusted backend service (bypassing RLS).
    This client is never used for auth actions (login/signup) to prevent token mutation.
    """
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


def get_auth_client() -> Client:
    """
    Return a fresh Supabase client instance specifically for auth requests (signup/login).
    This keeps the credentials mutation local to the auth request lifecycle.
    """
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY must be set in the environment."
        )
    return create_client(url, key)
