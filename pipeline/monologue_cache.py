"""
Monologue Cache
===============
Stores and retrieves the inner monologue generated at the start of each session.

The monologue is semantically session-scoped — it represents Aria "walking in"
to the conversation. It does not need to be regenerated on every message.

Cache invalidation rules:
  1. No record for this session_id → cache miss (generate fresh)
  2. Stored weight_tier is 'light' but current tier is 'full' → upgrade (regenerate)
  3. Monologue is older than MONOLOGUE_TTL_MINUTES → stale (regenerate)
  4. Everything else → cache hit (return stored text)
"""

from datetime import datetime, timezone, timedelta

from db.client import get_db

# How long a monologue stays valid within a session (minutes)
MONOLOGUE_TTL_MINUTES = 30


def get_cached_monologue(
    session_id: str,
    user_id: str,
    persona: str,
    current_weight_tier: str,
) -> str | None:
    """
    Returns the cached monologue text if valid, or None if it should be regenerated.

    current_weight_tier: 'light' or 'full'
    """
    db = get_db()
    result = (
        db.table("session_monologues")
        .select("monologue_text, weight_tier, created_at")
        .eq("session_id", session_id)
        .eq("user_id", user_id)
        .eq("persona", persona)
        .limit(1)
        .execute()
    )

    if not result.data:
        print("[MONO: cache miss — no record for session]")
        return None

    row = result.data[0]

    # Rule 2: tier upgrade needed (light → full)
    if row["weight_tier"] == "light" and current_weight_tier == "full":
        print("[MONO: cache miss — tier upgrade light→full]")
        return None

    # Rule 3: TTL check — stale if older than MONOLOGUE_TTL_MINUTES
    try:
        created = datetime.fromisoformat(
            row["created_at"].replace("Z", "+00:00")
        )
        age_minutes = (datetime.now(timezone.utc) - created).total_seconds() / 60
        if age_minutes > MONOLOGUE_TTL_MINUTES:
            print(f"[MONO: cache miss — stale ({age_minutes:.1f} min old)]")
            return None
    except Exception:
        # If we can't parse the timestamp, play it safe and regenerate
        print("[MONO: cache miss — could not parse created_at]")
        return None

    print("[MONO: cache hit]")
    return row["monologue_text"]


def save_monologue_cache(
    session_id: str,
    user_id: str,
    persona: str,
    monologue_text: str,
    weight_tier: str,
) -> None:
    """
    Upsert the generated monologue into the cache.
    weight_tier: 'light' or 'full'
    """
    db = get_db()
    row = {
        "session_id": session_id,
        "user_id": user_id,
        "persona": persona,
        "monologue_text": monologue_text,
        "weight_tier": weight_tier,
        "created_at": datetime.utcnow().isoformat(),
    }
    db.table("session_monologues").upsert(
        row, on_conflict="session_id,user_id,persona"
    ).execute()
    print(f"[MONO: cached (tier={weight_tier})]")
