"""
Layer 4 — Snapshot Engine
Every 20 turns, generates a Life Snapshot from the recent conversation batch.
Snapshots form the long-term relationship memory.

All operations are scoped by user_id + persona. No file I/O.
"""

import os
from datetime import datetime

from db.client import get_db
from .turn_store import get_all_turns
from .open_stories import get_open_stories

SNAPSHOT_INTERVAL = 20  # generate snapshot every N turns


# ── Snapshot Extraction (LLM) ─────────────────────────────────────────────────

def _generate_snapshot_llm(turns: list) -> dict:
    from openai import OpenAI
    import json

    transcript = ""
    for t in turns:
        transcript += f"{t['role'].upper()}: {t['content']}\n"

    prompt = f"""Analyze the exact conversation segment below and extract key information about the USER (the human).
Output strictly raw JSON without ANY markdown formatting or extra text.

CRITICAL MAPPING:
In the transcript below, USER is the human person whose life you are analyzing. ASSISTANT is Aria, the AI companion — do NOT extract facts about Aria.

Schema:
{{
  "facts_learned": ["semantic truth 1", "semantic truth 2"],
  "emotional_tone": "one word emotion (e.g. anxious, excited, neutral)",
  "events": ["event 1 narrative", "event 2 narrative"]
}}

Rules:
- facts_learned: Extract core facts about the USER's life (e.g., 'Likes pizza', 'Works as engineer'). Max 5. Exclude temporary states. Never include facts about the ASSISTANT.
- emotional_tone: The aggregate emotional undercurrent of the USER.
- events: Real things that happened to the USER. Max 3.

Transcript:
{transcript}"""

    try:
        client = OpenAI(
            api_key=os.environ["GROQ_API_KEY"],
            base_url="https://api.groq.com/openai/v1",
        )
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```json"):
            content = content.split("```json")[1].split("```")[0].strip()
        elif content.startswith("```"):
            content = content.split("```")[1].split("```")[0].strip()
        result = json.loads(content)
        return {
            "facts_learned": result.get("facts_learned", []),
            "emotional_tone": result.get("emotional_tone", "neutral"),
            "events": result.get("events", []),
        }
    except Exception as e:
        print(f"[Snapshot LLM Error] {e}")
        return {"facts_learned": [], "emotional_tone": "neutral", "events": []}


# ── Public API ────────────────────────────────────────────────────────────────

def should_generate_snapshot(turn_count: int, user_id: str, persona: str = "aria") -> bool:
    db = get_db()
    result = (
        db.table("snapshots")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("persona", persona)
        .execute()
    )
    snap_count = result.count or 0
    last_snapshot_turn = snap_count * SNAPSHOT_INTERVAL
    return turn_count >= last_snapshot_turn + SNAPSHOT_INTERVAL


def generate_snapshot(ebf: dict, user_id: str, persona: str = "aria", session_id: str = "", local_time: str = "") -> dict:
    """Generate a Life Snapshot from the most recent SNAPSHOT_INTERVAL turns."""
    all_turns = get_all_turns(user_id, persona)
    recent_turns = all_turns[-SNAPSHOT_INTERVAL:]

    now = datetime.utcnow()
    # Use local_time from client if available for accurate time_of_day
    try:
        if local_time:
            local_dt = datetime.fromisoformat(local_time)
            hour = local_dt.hour
        else:
            hour = now.hour
    except Exception:
        hour = now.hour
        
    if 5 <= hour < 12:
        time_of_day = "morning"
    elif 12 <= hour < 17:
        time_of_day = "afternoon"
    elif 17 <= hour < 21:
        time_of_day = "evening"
    else:
        time_of_day = "late night"

    llm_data = _generate_snapshot_llm(recent_turns)
    open_stories_data = get_open_stories(user_id, persona)

    snapshot_row = {
        "user_id": user_id,
        "persona": persona,
        "date": now.strftime("%Y-%m-%d"),
        "time_of_day": time_of_day,
        "facts_learned": llm_data["facts_learned"],
        "emotional_tone": llm_data["emotional_tone"],
        "energy_level": ebf.get("energy_level", "medium"),
        "events": llm_data["events"],
        "open_stories": [
            {
                "id": s.get("story_id", s.get("id", "")),
                "title": s["title"],
                "status": s["status"],
                "last_told": s["last_told"],
                "summary": s["summary"][:80],
            }
            for s in open_stories_data
        ],
        "behaviour_signal": ebf.get("dominant_emotion_pattern", ""),
        "communication_style": ebf.get("communication_style", "neutral"),
        "trust_level_at_snapshot": ebf.get("trust_level", 0.1),
    }

    db = get_db()
    db.table("snapshots").insert(snapshot_row).execute()
    return snapshot_row


def get_all_snapshots(user_id: str, persona: str = "aria") -> list:
    db = get_db()
    result = (
        db.table("snapshots")
        .select("*")
        .eq("user_id", user_id)
        .eq("persona", persona)
        .order("created_at")
        .execute()
    )
    return result.data


def get_accumulated_facts(user_id: str, persona: str = "aria") -> list:
    """Gather all unique facts across all snapshots."""
    all_facts = []
    for snap in get_all_snapshots(user_id, persona):
        for fact in snap.get("facts_learned", []):
            if fact not in all_facts:
                all_facts.append(fact)
    return all_facts
