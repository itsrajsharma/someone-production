"""
Layer 2 — Tension Detector
Tracks open loops: unresolved questions, stated goals not yet addressed,
emotional moments that were deflected, and conflicting constraints.
"""

import json
import os
import re
import uuid
from datetime import datetime

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "tensions.json")

# ── Persistence ───────────────────────────────────────────────────────────────

def _load() -> list:
    if not os.path.exists(DATA_PATH):
        return []
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def _save(loops: list):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(loops, f, indent=2, ensure_ascii=False)


# ── Detection Patterns ────────────────────────────────────────────────────────

_OPEN_QUESTION_STARTERS = [
    r"should i\b", r"what do you think\b", r"do you think\b",
    r"how do i\b", r"can i\b", r"is it worth\b", r"would you\b",
    r"what should\b", r"am i\b", r"why (do|did|is|am)\b",
]

_GOAL_STARTERS = [
    r"i want to\b", r"i'm trying to\b", r"my goal\b", r"i plan to\b",
    r"i hope to\b", r"i need to\b", r"i've been thinking about\b",
]

_DEFLECTION_PHRASES = [
    "anyway", "nevermind", "doesn't matter", "forget it",
    "let's not talk about", "moving on", "let's talk about something else",
]

_RESOLUTION_SIGNALS = [
    "thanks", "that makes sense", "i see", "got it", "ok", "yeah",
    "you're right", "i'll try", "i will", "makes sense", "understood",
    "exactly", "that's it", "perfect", "good point",
]


def _is_deflection(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in _DEFLECTION_PHRASES)


def _is_resolution(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in _RESOLUTION_SIGNALS)


# ── Public API ────────────────────────────────────────────────────────────────

def detect_tensions(user_message: str, bot_last_message: str = "") -> list:
    """
    Detect new tensions from the current user message.
    Returns list of newly created tension dicts.
    """
    loops = _load()
    new_loops = []
    lower = user_message.lower()

    # 1. Unanswered question (user asked something direct)
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
                loops.append(loop)
                new_loops.append(loop)
                break

    # 2. Stated goal not yet addressed
    for pattern in _GOAL_STARTERS:
        if re.search(pattern, lower):
            loop = {
                "id": str(uuid.uuid4())[:8],
                "type": "stated_goal",
                "summary": user_message[:80].strip(),
                "status": "open",
                "created_at": datetime.utcnow().isoformat(),
            }
            loops.append(loop)
            new_loops.append(loop)
            break

    # 3. Emotional deflection: user pivoted away from something heavy
    if _is_deflection(user_message) and bot_last_message:
        loop = {
            "id": str(uuid.uuid4())[:8],
            "type": "deflected_emotion",
            "summary": f"User deflected after: {bot_last_message[:60].strip()}",
            "status": "open",
            "created_at": datetime.utcnow().isoformat(),
        }
        loops.append(loop)
        new_loops.append(loop)

    _save(loops)
    return new_loops


def resolve_tensions(user_message: str) -> int:
    """
    Check if user message resolves any open loops.
    Returns count of newly resolved loops.
    """
    if not _is_resolution(user_message):
        return 0

    loops = _load()
    resolved_count = 0
    for loop in loops:
        if loop["status"] == "open":
            loop["status"] = "resolved"
            loop["resolved_at"] = datetime.utcnow().isoformat()
            resolved_count += 1

    _save(loops)
    return resolved_count


def get_open_loops() -> list:
    """Return all currently open tension loops."""
    return [l for l in _load() if l["status"] == "open"]


def get_top_open_loop() -> str:
    """Return a short summary of the most recent open loop (for scaffold)."""
    open_loops = get_open_loops()
    if not open_loops:
        return ""
    # Most recent
    latest = sorted(open_loops, key=lambda x: x["created_at"], reverse=True)[0]
    return f"{latest['type'].replace('_', ' ')}: {latest['summary'][:50]}"
