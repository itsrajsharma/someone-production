"""
Layer 1 — Turn Store
Stores every conversation turn with lightweight causal tags (topics, entities, intent).
These tags are used by the dependency resolver to find relevant past turns.

All functions are now scoped by user_id + persona (+ session_id where relevant).
No global state. No file I/O.
"""

import re
import time
import uuid
from datetime import datetime
from typing import Optional

from db.client import get_db


# ── Tag Extraction ────────────────────────────────────────────────────────────

_PERSON_PATTERNS = [
    r"\b(?:my\s+)?(?:friend|sister|brother|mom|dad|mother|father|boss|colleague|boyfriend|girlfriend|wife|husband)\b",
    r"\bnamed?\s+([A-Z][a-z]+)\b",
]
_GOAL_PHRASES = [
    "i want to", "i'm trying to", "i plan to", "my goal", "i hope to",
    "i've been thinking about", "i need to", "i want", "planning to",
]
_EMOTION_WORDS = {
    "positive": ["happy", "excited", "glad", "love", "great", "amazing", "good", "proud"],
    "negative": ["sad", "angry", "frustrated", "scared", "anxious", "worried", "stressed", "upset", "hurt", "lonely"],
    "neutral": ["okay", "fine", "alright", "whatever", "normal"],
}


def extract_tags(text: str) -> dict:
    """Extract lightweight causal tags from a message."""
    lower = text.lower()
    tags = {
        "topics": [],
        "entities": [],
        "intent": "statement",
        "emotion_valence": "neutral",
        "has_goal": False,
        "is_open_question": False,
    }

    if text.strip().endswith("?"):
        tags["intent"] = "question"
        tags["is_open_question"] = True

    for phrase in _GOAL_PHRASES:
        if phrase in lower:
            tags["has_goal"] = True
            tags["topics"].append("goal")
            break

    for valence, words in _EMOTION_WORDS.items():
        if any(w in lower for w in words):
            tags["emotion_valence"] = valence
            break

    for pattern in _PERSON_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        tags["entities"].extend([m.strip() for m in matches if m.strip()])

    topic_keywords = {
        "work": ["job", "work", "career", "office", "boss", "project", "deadline", "colleague"],
        "family": ["family", "sister", "brother", "mom", "dad", "mother", "father", "parents"],
        "relationships": ["friend", "girlfriend", "boyfriend", "wife", "husband", "partner", "love"],
        "health": ["gym", "workout", "sleep", "eat", "diet", "tired", "sick", "health"],
        "travel": ["travel", "trip", "visit", "city", "country", "flight", "vacation"],
        "emotions": ["feel", "feeling", "emotion", "mood", "stress", "happy", "sad"],
        "future": ["future", "plan", "goal", "dream", "aspire", "hope"],
    }
    for topic, kws in topic_keywords.items():
        if any(kw in lower for kw in kws):
            tags["topics"].append(topic)

    tags["topics"] = list(set(tags["topics"]))
    tags["entities"] = list(set(tags["entities"]))
    return tags


# ── Session Facts ─────────────────────────────────────────────────────────────

def extract_session_facts(user_message: str, user_id: str, session_id: str, persona: str = "aria"):
    """Extract and persist session-scoped facts from user message."""
    from openai import OpenAI
    import json
    import os

    prompt = f"""Extract any implicit or explicit session facts (transient state, current actions, corrections, or immediate plans) from this user message.
Output strictly raw JSON without ANY markdown formatting.
Schema:
{{
  "new_facts": ["fact 1", "fact 2"] 
}}

Rules:
- Focus on what the user is doing actively, corrections they make, or states they declare.
- Keep each fact under 40 characters.
- If there are no concrete facts or activities, output an empty array.

User Message: "{user_message.strip()}"
"""
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
        new_facts = result.get("new_facts", [])
    except Exception as e:
        print(f"[Session Facts LLM Error] {e}")
        new_facts = []

    if not new_facts:
        return

    # Enforce max 10 facts per session: get current count, delete oldest if needed
    db = get_db()
    existing = (
        db.table("session_facts")
        .select("id, fact")
        .eq("user_id", user_id)
        .eq("session_id", session_id)
        .eq("persona", persona)
        .order("created_at")
        .execute()
    )
    existing_facts = [r["fact"] for r in existing.data]

    rows_to_insert = []
    for f in new_facts:
        f = f.strip()
        if f and f not in existing_facts:
            rows_to_insert.append({
                "user_id": user_id,
                "session_id": session_id,
                "persona": persona,
                "fact": f,
            })
            existing_facts.append(f)

    if rows_to_insert:
        db.table("session_facts").insert(rows_to_insert).execute()

    # Trim to 10 most recent
    all_ids = [r["id"] for r in existing.data]
    total = len(all_ids) + len(rows_to_insert)
    if total > 10:
        overage = total - 10
        ids_to_delete = all_ids[:overage]
        if ids_to_delete:
            db.table("session_facts").delete().in_("id", ids_to_delete).execute()


def get_session_facts(user_id: str, session_id: str, persona: str = "aria") -> list:
    """Return all session facts for this user+session."""
    db = get_db()
    result = (
        db.table("session_facts")
        .select("fact")
        .eq("user_id", user_id)
        .eq("session_id", session_id)
        .eq("persona", persona)
        .order("created_at")
        .execute()
    )
    return [r["fact"] for r in result.data]


# ── Public API ────────────────────────────────────────────────────────────────

def save_turn(
    role: str,
    content: str,
    user_id: str,
    session_id: str,
    persona: str = "aria",
) -> dict:
    """Save a turn with its causal tags. Returns the saved turn dict."""
    if role == "user":
        extract_session_facts(content, user_id, session_id, persona)

    turn_id = str(uuid.uuid4())[:8]
    turn = {
        "id": turn_id,
        "user_id": user_id,
        "persona": persona,
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat(),
        "causal_tags": extract_tags(content),
    }
    db = get_db()
    result = db.table("turns").insert(turn).execute()
    # Return the row with its pk
    saved = result.data[0] if result.data else turn
    return saved


def get_all_turns(user_id: str, persona: str = "aria") -> list:
    """Return all turns for a user+persona in chronological order."""
    db = get_db()
    result = (
        db.table("turns")
        .select("*")
        .eq("user_id", user_id)
        .eq("persona", persona)
        .order("timestamp")
        .execute()
    )
    return result.data


def get_turn_count(user_id: str, persona: str = "aria") -> int:
    """Return total number of turns for a user+persona."""
    db = get_db()
    result = (
        db.table("turns")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("persona", persona)
        .execute()
    )
    return result.count or 0


def clear_session(user_id: str, session_id: str, persona: str = "aria"):
    """Clear session facts for a session (called on explicit logout/reset)."""
    db = get_db()
    db.table("session_facts").delete().eq("user_id", user_id).eq("session_id", session_id).eq("persona", persona).execute()
