"""
Layer 5 — Core Identity Engine
Generates a permanent, continuously evolving psychological profile
by analyzing the chronological timeline of snapshots.

All operations are scoped by user_id. No file I/O.
"""

import os
from datetime import datetime

from db.client import get_db
from .snapshot_engine import get_all_snapshots
from .llm_client import get_fast_client

UPDATE_INTERVAL_SNAPSHOTS = 2  # Update identity every 2 snapshots (~20 turns)

_DEFAULT_IDENTITY = {
    "snapshot_count_at_last_update": 0,
    "psychological_profile": "No profile exists yet.",
    "current_life_chapter": "Unknown.",
    "enduring_traits": [],
}


# ── Persistence ───────────────────────────────────────────────────────────────

def _load(user_id: str) -> dict:
    db = get_db()
    result = (
        db.table("core_identity")
        .select("*")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if result.data:
        row = result.data[0]
        return {
            "snapshot_count_at_last_update": row.get("snapshot_count_at_last_update", 0),
            "psychological_profile": row.get("psychological_profile", _DEFAULT_IDENTITY["psychological_profile"]),
            "current_life_chapter": row.get("current_life_chapter", _DEFAULT_IDENTITY["current_life_chapter"]),
            "enduring_traits": row.get("enduring_traits", []),
        }
    return dict(_DEFAULT_IDENTITY)


def _save(identity: dict, user_id: str):
    db = get_db()
    row = {
        "user_id": user_id,
        "snapshot_count_at_last_update": identity["snapshot_count_at_last_update"],
        "psychological_profile": identity["psychological_profile"],
        "current_life_chapter": identity["current_life_chapter"],
        "enduring_traits": identity["enduring_traits"],
        "last_updated": datetime.utcnow().isoformat(),
    }
    db.table("core_identity").upsert(row, on_conflict="user_id").execute()


# ── Identity Synthesis ────────────────────────────────────────────────────────

def update_identity_if_needed(user_id: str, persona: str = "aria"):
    from openai import OpenAI
    import json

    snapshots = get_all_snapshots(user_id, persona)
    current_count = len(snapshots)
    identity = _load(user_id)
    last_update_count = identity.get("snapshot_count_at_last_update", 0)

    if current_count < last_update_count + UPDATE_INTERVAL_SNAPSHOTS:
        return

    recent_snaps = snapshots[-6:]
    if not recent_snaps:
        return

    timeline = ""
    for s in recent_snaps:
        timeline += f"\nDATE: {s.get('date', 'Unknown')}\n"
        timeline += f"EMOTIONAL TONE: {s.get('emotional_tone', 'neutral')}\n"
        timeline += f"EVENTS: {', '.join(s.get('events', []))}\n"
        timeline += f"FACTS: {', '.join(s.get('facts_learned', []))}\n"

    prompt = f"""You are analyzing a human's life timeline based on recent conversation snapshots.
Synthesize a deep, grounded psychological understanding of this user along with their spatial/daily schedule.
Output strictly raw JSON without ANY markdown formatting.
Schema:
{{
  "psychological_profile": "A deeply empathetic, 2-3 sentence biography evaluating their personality, sensitivities, and how they think.",
  "daily_routine": ["Works late nights", "Goes to office at 9 AM"],
  "current_life_chapter": "A 1-2 sentence summary of what overarching phase they are currently in.",
  "enduring_traits": ["Trait 1", "Trait 2"]
}}

Timeline:
{timeline}
"""
    try:
        client, _fast_model = get_fast_client()
        response = client.chat.completions.create(
            model=_fast_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```json"):
            content = content.split("```json")[1].split("```")[0].strip()
        elif content.startswith("```"):
            content = content.split("```")[1].split("```")[0].strip()
        result = json.loads(content)
        parsed_profile = result.get("psychological_profile", identity["psychological_profile"])
        routine_array = result.get("daily_routine", [])
        if routine_array:
            parsed_profile += "\n\nDAILY ROUTINE:\n" + "\n".join(f"- {r}" for r in routine_array)
            
        identity["psychological_profile"] = parsed_profile
        identity["current_life_chapter"] = result.get("current_life_chapter", identity["current_life_chapter"])
        identity["enduring_traits"] = result.get("enduring_traits", identity["enduring_traits"])
    except Exception as e:
        print(f"[Identity LLM Error] {e}")

    identity["snapshot_count_at_last_update"] = current_count
    _save(identity, user_id)


def get_core_identity(user_id: str) -> dict:
    return _load(user_id)
