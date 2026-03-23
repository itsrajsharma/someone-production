"""
Layer 4 — Snapshot Engine
Every 10-12 turns, generates a Life Snapshot from the recent conversation batch.
Snapshots form the long-term relationship memory.
"""

import json
import os
import re
from datetime import datetime

from .turn_store import get_all_turns
from .open_stories import get_open_stories

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "snapshots.json")
SNAPSHOT_INTERVAL = 10  # generate snapshot every N turns

# ── Persistence ───────────────────────────────────────────────────────────────

def _load() -> list:
    if not os.path.exists(DATA_PATH):
        return []
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def _save(snapshots: list):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(snapshots, f, indent=2, ensure_ascii=False)


# ── Fact Extraction ───────────────────────────────────────────────────────────

_FACT_PATTERNS = [
    (r"my name is ([A-Za-z\s]+)", "name: {}"),
    (r"i(?:'m| am) ([0-9]+)(?: years old)?", "age: {}"),
    (r"i (?:work|am working) (?:at|for|as) ([A-Za-z\s]+)", "works at: {}"),
    (r"i live in ([A-Za-z\s,]+)", "lives in: {}"),
    (r"i(?:'m| am) from ([A-Za-z\s,]+)", "from: {}"),
    (r"my (?:favourite|favorite|fav) (?:place|city|country) is ([A-Za-z\s]+)", "fav place: {}"),
    (r"my (?:favourite|favorite|fav) (?:food|fruit|dish) is ([A-Za-z\s]+)", "fav food: {}"),
    (r"i (?:have|'ve got) (?:a|an) (younger|older)? (?:sister|brother)", "has {0} sibling"),
    (r"i (?:don't|do not) like ([A-Za-z\s]+)", "dislikes: {}"),
    (r"i (?:love|enjoy|like) ([A-Za-z\s]+)", "likes: {}"),
]


def _extract_facts(turns: list) -> list:
    facts = []
    for turn in turns:
        if turn["role"] != "user":
            continue
        text = turn["content"]
        for pattern, template in _FACT_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if match.lastindex:
                    fact = template.format(*[g.strip() for g in match.groups() if g])
                else:
                    fact = template.format(match.group(0).strip())
                if fact not in facts:
                    facts.append(fact)
    return facts[:8]  # cap at 8 facts per snapshot


def _dominant_emotion(turns: list) -> str:
    """Rough dominant emotion from the batch of turns."""
    emotion_counts = {}
    for turn in turns:
        valence = turn.get("causal_tags", {}).get("emotion_valence", "neutral")
        emotion_counts[valence] = emotion_counts.get(valence, 0) + 1
    if not emotion_counts:
        return "neutral"
    return max(emotion_counts, key=emotion_counts.get)


def _extract_events(turns: list) -> list:
    """Pull out notable events mentioned by the user."""
    events = []
    event_patterns = [
        r"i (had|went|started|finished|got|broke|quit|left|bought|lost|found|met)",
        r"today (i|we|they|it)",
        r"yesterday (i|we|they|it)",
        r"(the|a) (?:fight|argument|meeting|interview|date|trip|job|project)",
    ]
    for turn in turns:
        if turn["role"] != "user":
            continue
        for pattern in event_patterns:
            if re.search(pattern, turn["content"], re.IGNORECASE):
                events.append(turn["content"][:60].strip())
                break
    return list(dict.fromkeys(events))[:5]  # unique, max 5


# ── Public API ────────────────────────────────────────────────────────────────

def should_generate_snapshot(turn_count: int) -> bool:
    snapshots = _load()
    last_snapshot_turn = len(snapshots) * SNAPSHOT_INTERVAL
    return turn_count >= last_snapshot_turn + SNAPSHOT_INTERVAL


def generate_snapshot(ebf: dict) -> dict:
    """
    Generate a Life Snapshot from the most recent SNAPSHOT_INTERVAL turns.
    Returns the snapshot dict.
    """
    all_turns = get_all_turns()
    recent_turns = all_turns[-SNAPSHOT_INTERVAL:]

    now = datetime.utcnow()
    hour = now.hour
    if 5 <= hour < 12:
        time_of_day = "morning"
    elif 12 <= hour < 17:
        time_of_day = "afternoon"
    elif 17 <= hour < 21:
        time_of_day = "evening"
    else:
        time_of_day = "late night"

    snapshot = {
        "date": now.strftime("%Y-%m-%d"),
        "time_of_day": time_of_day,
        "facts_learned": _extract_facts(recent_turns),
        "emotional_tone": _dominant_emotion(recent_turns),
        "energy_level": ebf.get("energy_level", "medium"),
        "events": _extract_events(recent_turns),
        "open_stories": [
            {
                "id": s["id"],
                "title": s["title"],
                "status": s["status"],
                "last_told": s["last_told"],
                "summary": s["summary"][:80],
            }
            for s in get_open_stories()
        ],
        "behaviour_signal": ebf.get("dominant_emotion_pattern", ""),
        "communication_style": ebf.get("communication_style", "neutral"),
        "trust_level_at_snapshot": ebf.get("trust_level", 0.1),
    }

    snapshots = _load()
    snapshots.append(snapshot)
    _save(snapshots)
    return snapshot


def get_all_snapshots() -> list:
    return _load()


def get_accumulated_facts() -> list:
    """Gather all unique facts across all snapshots."""
    all_facts = []
    for snap in _load():
        for fact in snap.get("facts_learned", []):
            if fact not in all_facts:
                all_facts.append(fact)
    return all_facts
