"""
Layer 4 — Behavioural Rhythm Profile
Builds a profile of when the user is most open, stressed, or storytelling,
by aggregating patterns across Life Snapshots.

All operations are scoped by user_id + persona. No file I/O.
"""

from collections import defaultdict
from datetime import datetime

from db.client import get_db

_DEFAULT_RHYTHM = {
    "most_open_time": "unknown",
    "most_stressed_day": "unknown",
    "storytelling_frequency": "unknown",
    "trust_growth_rate": "unknown",
    "session_times": [],
    "snapshot_count": 0,
}


# ── Persistence ───────────────────────────────────────────────────────────────

def _load(user_id: str, persona: str = "aria") -> dict:
    db = get_db()
    result = (
        db.table("behaviour_rhythm")
        .select("*")
        .eq("user_id", user_id)
        .eq("persona", persona)
        .limit(1)
        .execute()
    )
    if result.data:
        row = result.data[0]
        return {**_DEFAULT_RHYTHM, **{k: v for k, v in row.items() if k in _DEFAULT_RHYTHM}}
    return dict(_DEFAULT_RHYTHM)


def _save(rhythm: dict, user_id: str, persona: str = "aria"):
    db = get_db()
    row = {
        "user_id": user_id,
        "persona": persona,
        "most_open_time": rhythm.get("most_open_time", "unknown"),
        "most_stressed_day": rhythm.get("most_stressed_day", "unknown"),
        "storytelling_frequency": rhythm.get("storytelling_frequency", "unknown"),
        "trust_growth_rate": rhythm.get("trust_growth_rate", "unknown"),
        "session_times": rhythm.get("session_times", []),
        "snapshot_count": rhythm.get("snapshot_count", 0),
        "last_updated": datetime.utcnow().isoformat(),
    }
    db.table("behaviour_rhythm").upsert(row, on_conflict="user_id,persona").execute()


# ── Analysis ──────────────────────────────────────────────────────────────────

def _most_common(items: list):
    if not items:
        return "unknown"
    counts = defaultdict(int)
    for item in items:
        counts[item] += 1
    return max(counts, key=counts.get)


# ── Public API ────────────────────────────────────────────────────────────────

def update_rhythm(snapshot: dict, user_id: str, persona: str = "aria") -> dict:
    """Update the Behavioural Rhythm Profile from a newly generated snapshot."""
    rhythm = _load(user_id, persona)
    rhythm["snapshot_count"] += 1

    rhythm["session_times"].append({
        "time_of_day": snapshot.get("time_of_day", "unknown"),
        "trust": snapshot.get("trust_level_at_snapshot", 0.1),
        "tone": snapshot.get("emotional_tone", "neutral"),
        "num_stories": len(snapshot.get("open_stories", [])),
    })

    sessions = rhythm["session_times"]

    time_trust = defaultdict(list)
    for s in sessions:
        time_trust[s["time_of_day"]].append(s["trust"])

    if time_trust:
        avg_trust_by_time = {t: sum(v) / len(v) for t, v in time_trust.items()}
        rhythm["most_open_time"] = max(avg_trust_by_time, key=avg_trust_by_time.get)

    if len(sessions) >= 2:
        trust_values = [s["trust"] for s in sessions]
        delta = trust_values[-1] - trust_values[0]
        if delta > 0.3:
            rhythm["trust_growth_rate"] = "fast"
        elif delta > 0.1:
            rhythm["trust_growth_rate"] = "moderate"
        else:
            rhythm["trust_growth_rate"] = "slow"

    if sessions:
        avg_stories = sum(s["num_stories"] for s in sessions) / len(sessions)
        if avg_stories > 2:
            rhythm["storytelling_frequency"] = "high"
        elif avg_stories > 0.5:
            rhythm["storytelling_frequency"] = "moderate"
        else:
            rhythm["storytelling_frequency"] = "low"

    _save(rhythm, user_id, persona)
    return rhythm


def get_rhythm(user_id: str, persona: str = "aria") -> dict:
    return _load(user_id, persona)


def get_rhythm_hint(user_id: str, persona: str = "aria") -> str:
    """Brief hint for the scaffold about user's current context."""
    rhythm = _load(user_id, persona)
    now_hour = datetime.utcnow().hour
    if 22 <= now_hour or now_hour < 2:
        return f"late night — user tends to be: {rhythm.get('most_open_time', 'unknown')} then"
    return ""
