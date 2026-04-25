"""
Layer 2 — Tension Detector
Tracks open loops: unresolved questions, stated goals not yet addressed,
emotional moments that were deflected, and conflicting constraints.

All operations are scoped by user_id + persona. No file I/O.
"""

import re
import uuid
from datetime import datetime

from db.client import get_db


# ── Detection Patterns ────────────────────────────────────────────────────────

_OPEN_QUESTION_STARTERS = [
    r"should i\b", r"what do you think\b", r"do you think\b",
    r"how do i\b", r"can i\b", r"is it worth\b", r"would you\b",
    r"what should\b", r"am i\b", r"why (do|did|is|am)\b",
    r"is it normal\b", r"does it mean\b", r"how comes\b", r"am i wrong\b",
    r"is that weird\b", r"should we\b",
]

_GOAL_STARTERS = [
    r"i want to\b", r"i'm trying to\b", r"my goal\b", r"i plan to\b",
    r"i hope to\b", r"i need to\b", r"i've been thinking about\b",
    r"maybe i should\b", r"i really wanna\b", r"i gotta\b", r"i must\b",
    r"i am determined to\b", r"i'm gonna\b",
]

_DEFLECTION_PHRASES = [
    "anyway", "nevermind", "doesn't matter", "forget it",
    "let's not talk about", "moving on", "let's talk about something else",
    "whatever", "it's fine", "it is what it is", "i don't care anymore",
    "stop talking about", "drop it", "shrugs", "oh well",
]

_RESOLUTION_SIGNALS = [
    "thanks", "that makes sense", "i see", "got it", "ok", "yeah",
    "you're right", "i'll try", "i will", "makes sense", "understood",
    "exactly", "that's it", "perfect", "good point",
    "i feel better", "agreed", "let's do that", "that helps", "helpful",
]


def _is_deflection(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in _DEFLECTION_PHRASES)


def _is_resolution(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in _RESOLUTION_SIGNALS)


# ── Persistence ───────────────────────────────────────────────────────────────

def _load(user_id: str, persona: str = "aria") -> list:
    db = get_db()
    result = (
        db.table("tensions")
        .select("*")
        .eq("user_id", user_id)
        .eq("persona", persona)
        .order("created_at")
        .execute()
    )
    return result.data


def _insert_tension(tension: dict, user_id: str, persona: str):
    db = get_db()
    row = {
        "tension_id": tension["id"],
        "user_id": user_id,
        "persona": persona,
        "type": tension["type"],
        "summary": tension["summary"],
        "status": tension["status"],
        "created_at": tension["created_at"],
    }
    db.table("tensions").upsert(row, on_conflict="tension_id,user_id").execute()


def _update_tension_status(tension_id: str, user_id: str, resolved_at: str):
    db = get_db()
    db.table("tensions").update({
        "status": "resolved",
        "resolved_at": resolved_at,
    }).eq("tension_id", tension_id).eq("user_id", user_id).execute()


# ── Public API ────────────────────────────────────────────────────────────────

def detect_tensions(
    user_message: str,
    bot_last_message: str = "",
    user_id: str = "",
    persona: str = "aria",
) -> list:
    """Detect new tensions from the current user message. Returns newly created tension dicts."""
    new_loops = []
    lower = user_message.lower()

    # 1. Unanswered question
    if user_message.strip().endswith("?"):
        for pattern in _OPEN_QUESTION_STARTERS:
            if re.search(pattern, lower):
                loop = {
                    "id": str(uuid.uuid4())[:8],
                    "type": "open_question",
                    "summary": user_message[:80].strip(),
                    "status": "open",
                    "created_at": datetime.utcnow().isoformat(),
                }
                _insert_tension(loop, user_id, persona)
                new_loops.append(loop)
                break

    # 2. Stated goal
    for pattern in _GOAL_STARTERS:
        if re.search(pattern, lower):
            loop = {
                "id": str(uuid.uuid4())[:8],
                "type": "stated_goal",
                "summary": user_message[:80].strip(),
                "status": "open",
                "created_at": datetime.utcnow().isoformat(),
            }
            _insert_tension(loop, user_id, persona)
            new_loops.append(loop)
            break

    # 3. Emotional deflection
    if _is_deflection(user_message) and bot_last_message:
        loop = {
            "id": str(uuid.uuid4())[:8],
            "type": "deflected_emotion",
            "summary": f"User deflected after: {bot_last_message[:60].strip()}",
            "status": "open",
            "created_at": datetime.utcnow().isoformat(),
        }
        _insert_tension(loop, user_id, persona)
        new_loops.append(loop)

    return new_loops


def resolve_tensions(user_message: str, user_id: str, persona: str = "aria") -> int:
    """Check if user message resolves any open loops. Returns count of newly resolved loops."""
    if not _is_resolution(user_message):
        return 0

    loops = _load(user_id, persona)
    resolved_count = 0
    now = datetime.utcnow().isoformat()
    for loop in loops:
        if loop["status"] == "open":
            _update_tension_status(loop["tension_id"], user_id, now)
            resolved_count += 1

    return resolved_count


def get_open_loops(user_id: str, persona: str = "aria") -> list:
    """Return all currently open tension loops."""
    return [l for l in _load(user_id, persona) if l["status"] == "open"]


def get_top_open_loop(user_id: str, persona: str = "aria") -> str:
    """Return a short summary of the most recent open loop (for scaffold)."""
    open_loops = get_open_loops(user_id, persona)
    if not open_loops:
        return ""
    latest = sorted(open_loops, key=lambda x: x.get("created_at", ""), reverse=True)[0]
    loop_type = latest.get("type", "").replace("_", " ")
    return f"{loop_type}: {latest['summary'][:50]}"
