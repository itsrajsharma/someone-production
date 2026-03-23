"""
Layer 1 — Turn Store
Stores every conversation turn with lightweight causal tags (topics, entities, intent).
These tags are used by the dependency resolver to find relevant past turns.
"""

import json
import os
import re
import time
import uuid
from datetime import datetime

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "turns.json")


def _load() -> list:
    if not os.path.exists(DATA_PATH):
        return []
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def _save(turns: list):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(turns, f, indent=2, ensure_ascii=False)


# ── Tag Extraction ────────────────────────────────────────────────────────────

# Simple named-entity / topic keywords (no ML needed)
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

    # Intent detection
    if text.strip().endswith("?"):
        tags["intent"] = "question"
        tags["is_open_question"] = True

    # Goal detection
    for phrase in _GOAL_PHRASES:
        if phrase in lower:
            tags["has_goal"] = True
            tags["topics"].append("goal")
            break

    # Emotion valence
    for valence, words in _EMOTION_WORDS.items():
        if any(w in lower for w in words):
            tags["emotion_valence"] = valence
            break

    # Entity extraction (simple pattern)
    for pattern in _PERSON_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        tags["entities"].extend([m.strip() for m in matches if m.strip()])

    # Topic keywords (nouns / domain areas via simple wordlist)
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


# ── Public API ────────────────────────────────────────────────────────────────

def save_turn(role: str, content: str) -> dict:
    """Save a turn with its causal tags. Returns the saved turn."""
    turns = _load()
    turn = {
        "id": str(uuid.uuid4())[:8],
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat(),
        "causal_tags": extract_tags(content),
    }
    turns.append(turn)
    _save(turns)
    return turn


def get_all_turns() -> list:
    return _load()


def get_turn_count() -> int:
    return len(_load())


def clear_session():
    """Optionally wipe turns for a fresh session (not used by default)."""
    _save([])
