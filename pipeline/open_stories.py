"""
Layer 4 — Open Stories
Tracks unfinished narratives (conflicts, dreams, projects, relationships).
Detects them at write time and reactivates them when the user's new message
is semantically connected.
"""

import json
import os
import re
import uuid
from datetime import datetime

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "open_stories.json")

REACTIVATION_THRESHOLD = 0.25  # cosine similarity threshold

# ── Persistence ───────────────────────────────────────────────────────────────

def _load() -> list:
    if not os.path.exists(DATA_PATH):
        return []
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def _save(stories: list):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(stories, f, indent=2, ensure_ascii=False)


# ── Detection Patterns ────────────────────────────────────────────────────────

_STORY_TRIGGERS = [
    r"had a (fight|argument|fallout|disagreement) with\b",
    r"i've been (dealing with|going through|struggling with)\b",
    r"there's this (situation|thing|problem|issue)\b",
    r"i (broke up|quit|lost|missed|failed)\b",
    r"(my|a) (friend|sister|brother|boss|partner) (said|did|told|left|hurt)\b",
    r"i've been (thinking about|wanting to|trying to)\b",
    r"i want to (change|leave|start|quit|build|create)\b",
    r"this (project|idea|dream|plan) (i have|i've been)\b",
    r"i'm (scared|worried|nervous) (about|that)\b",
]


def _extract_story_title(text: str) -> str:
    """Create a short title for a detected story."""
    # Take first meaningful chunk
    clean = re.sub(r"[^\w\s]", "", text).strip()
    words = clean.split()[:6]
    return " ".join(words).lower()


# ── Public API ────────────────────────────────────────────────────────────────

def detect_and_save_story(user_message: str) -> dict | None:
    """
    If the user message contains an open story pattern, save it.
    Returns the new story dict or None.
    """
    lower = user_message.lower()
    for pattern in _STORY_TRIGGERS:
        if re.search(pattern, lower):
            stories = _load()
            # Avoid duplicate stories (similar text already stored)
            for s in stories:
                if s["status"] == "open" and cosine_sim(user_message, s["summary"]) > 0.6:
                    return None  # Already tracking this

            story = {
                "id": f"story_{str(uuid.uuid4())[:6]}",
                "title": _extract_story_title(user_message),
                "status": "open",
                "first_told": datetime.utcnow().isoformat(),
                "last_told": datetime.utcnow().isoformat(),
                "summary": user_message[:120].strip(),
            }
            stories.append(story)
            _save(stories)
            return story
    return None


def cosine_sim(text_a: str, text_b: str) -> float:
    """Compute cosine similarity between two text strings."""
    try:
        vec = TfidfVectorizer(stop_words="english", min_df=1)
        matrix = vec.fit_transform([text_a, text_b])
        return float(cosine_similarity(matrix[0], matrix[1])[0][0])
    except Exception:
        return 0.0


def check_reactivation(current_message: str) -> dict | None:
    """
    Check if the current message is semantically connected to any open story.
    Returns the reactivated story dict or None.
    """
    stories = [s for s in _load() if s["status"] == "open"]
    if not stories:
        return None

    best_match = None
    best_score = REACTIVATION_THRESHOLD  # minimum to trigger

    for story in stories:
        score = cosine_sim(current_message, story["summary"])
        if score > best_score:
            best_score = score
            best_match = story

    if best_match:
        # Update last_told timestamp
        all_stories = _load()
        for s in all_stories:
            if s["id"] == best_match["id"]:
                s["last_told"] = datetime.utcnow().isoformat()
        _save(all_stories)

    return best_match


def resolve_story(story_id: str):
    """Mark a story as resolved."""
    stories = _load()
    for s in stories:
        if s["id"] == story_id:
            s["status"] = "resolved"
            s["resolved_at"] = datetime.utcnow().isoformat()
    _save(stories)


def get_open_stories() -> list:
    return [s for s in _load() if s["status"] == "open"]
