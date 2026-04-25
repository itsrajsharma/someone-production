"""
Layer 4 — Open Stories
Tracks unfinished narratives (conflicts, dreams, projects, relationships).
Detects them at write time and reactivates them when the user's new message
is semantically connected.

All operations are scoped by user_id + persona. No file I/O.
"""

import re
import uuid
from datetime import datetime

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from db.client import get_db

REACTIVATION_THRESHOLD = 0.25

# ── Detection Patterns ────────────────────────────────────────────────────────

_STORY_TRIGGERS = [
    r"had a (fight|argument|fallout|disagreement|moment|weird encounter) with\b",
    r"i've been (dealing with|going through|struggling with|putting up with|suffering from)\b",
    r"there's this (situation|thing|problem|issue|drama|guy|girl|person)\b",
    r"i (broke up|quit|lost|missed|failed|screwed up|messed up)\b",
    r"(my|a) (friend|sister|brother|boss|partner|colleague|coworker) (said|did|told|left|hurt|complained)\b",
    r"i've been (thinking about|wanting to|trying to|dreaming of|considering)\b",
    r"i want to (change|leave|start|quit|build|create|fix|confront)\b",
    r"this (project|idea|dream|plan|goal|company) (i have|i've been)\b",
    r"i'm (scared|worried|nervous|terrified|anxious|angry) (about|that)\b",
    r"(remind me|i'll tell you) (later|tomorrow|another time)\b",
    r"long story short\b",
    r"it's a long story\b",
    r"i have a lot to (say|tell you|vent about)\b",
]


def _extract_story_title(text: str) -> str:
    clean = re.sub(r"[^\w\s]", "", text).strip()
    words = clean.split()[:6]
    return " ".join(words).lower()


# ── Helpers ───────────────────────────────────────────────────────────────────

def cosine_sim(text_a: str, text_b: str) -> float:
    try:
        vec = TfidfVectorizer(stop_words="english", min_df=1)
        matrix = vec.fit_transform([text_a, text_b])
        return float(cosine_similarity(matrix[0], matrix[1])[0][0])
    except Exception:
        return 0.0


# ── Persistence ───────────────────────────────────────────────────────────────

def _load(user_id: str, persona: str = "aria") -> list:
    db = get_db()
    result = (
        db.table("open_stories")
        .select("*")
        .eq("user_id", user_id)
        .eq("persona", persona)
        .order("first_told")
        .execute()
    )
    return result.data


# ── Public API ────────────────────────────────────────────────────────────────

def detect_and_save_story(
    user_message: str,
    user_id: str,
    persona: str = "aria",
) -> dict | None:
    """If the user message contains an open story pattern, save it. Returns new story or None."""
    lower = user_message.lower()
    for pattern in _STORY_TRIGGERS:
        if re.search(pattern, lower):
            stories = _load(user_id, persona)
            # Avoid duplicate stories
            for s in stories:
                if s["status"] == "open" and cosine_sim(user_message, s["summary"]) > 0.6:
                    return None

            story_id = f"story_{str(uuid.uuid4())[:6]}"
            now = datetime.utcnow().isoformat()
            story = {
                "story_id": story_id,
                "user_id": user_id,
                "persona": persona,
                "title": _extract_story_title(user_message),
                "status": "open",
                "first_told": now,
                "last_told": now,
                "summary": user_message[:120].strip(),
            }
            db = get_db()
            db.table("open_stories").insert(story).execute()
            return story
    return None


def check_reactivation(
    current_message: str,
    user_id: str,
    persona: str = "aria",
) -> dict | None:
    """Check if the current message is semantically connected to any open story."""
    stories = [s for s in _load(user_id, persona) if s["status"] == "open"]
    if not stories:
        return None

    best_match = None
    best_score = REACTIVATION_THRESHOLD

    for story in stories:
        score = cosine_sim(current_message, story["summary"])
        if score > best_score:
            best_score = score
            best_match = story

    if best_match:
        db = get_db()
        db.table("open_stories").update({
            "last_told": datetime.utcnow().isoformat()
        }).eq("story_id", best_match["story_id"]).eq("user_id", user_id).execute()

    return best_match


def resolve_story(story_id: str, user_id: str):
    """Mark a story as resolved."""
    db = get_db()
    db.table("open_stories").update({
        "status": "resolved",
        "resolved_at": datetime.utcnow().isoformat(),
    }).eq("story_id", story_id).eq("user_id", user_id).execute()


def get_open_stories(user_id: str, persona: str = "aria") -> list:
    return [s for s in _load(user_id, persona) if s["status"] == "open"]
