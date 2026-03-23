"""
Layer 4 — Behavioural Rhythm Profile
Builds a profile of when the user is most open, stressed, or storytelling,
by aggregating patterns across Life Snapshots.
"""

import json
import os
from collections import defaultdict
from datetime import datetime

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "rhythm.json")

_DEFAULT_RHYTHM = {
    "most_open_time": "unknown",
    "most_stressed_day": "unknown",
    "storytelling_frequency": "unknown",
    "trust_growth_rate": "unknown",
    "last_updated": "",
    "session_times": [],         # list of {"time_of_day": ..., "trust": ...}
    "snapshot_count": 0,
}

# ── Persistence ───────────────────────────────────────────────────────────────

def _load() -> dict:
    if not os.path.exists(DATA_PATH):
        return dict(_DEFAULT_RHYTHM)
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            return {**_DEFAULT_RHYTHM, **data}
        except json.JSONDecodeError:
            return dict(_DEFAULT_RHYTHM)


def _save(rhythm: dict):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    rhythm["last_updated"] = datetime.utcnow().isoformat()
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(rhythm, f, indent=2, ensure_ascii=False)


# ── Analysis ──────────────────────────────────────────────────────────────────

def _most_common(items: list):
    if not items:
        return "unknown"
    counts = defaultdict(int)
    for item in items:
        counts[item] += 1
    return max(counts, key=counts.get)


# ── Public API ────────────────────────────────────────────────────────────────

def update_rhythm(snapshot: dict):
    """
    Update the Behavioural Rhythm Profile from a newly generated snapshot.
    """
    rhythm = _load()
    rhythm["snapshot_count"] += 1

    # Record session time + trust level
    rhythm["session_times"].append({
        "time_of_day": snapshot.get("time_of_day", "unknown"),
        "trust": snapshot.get("trust_level_at_snapshot", 0.1),
        "tone": snapshot.get("emotional_tone", "neutral"),
        "num_stories": len(snapshot.get("open_stories", [])),
    })

    sessions = rhythm["session_times"]

    # Most open time: highest average trust by time_of_day
    time_trust = defaultdict(list)
    for s in sessions:
        time_trust[s["time_of_day"]].append(s["trust"])

    if time_trust:
        avg_trust_by_time = {t: sum(v) / len(v) for t, v in time_trust.items()}
        rhythm["most_open_time"] = max(avg_trust_by_time, key=avg_trust_by_time.get)

    # Trust growth rate
    if len(sessions) >= 2:
        trust_values = [s["trust"] for s in sessions]
        delta = trust_values[-1] - trust_values[0]
        if delta > 0.3:
            rhythm["trust_growth_rate"] = "fast"
        elif delta > 0.1:
            rhythm["trust_growth_rate"] = "moderate"
        else:
            rhythm["trust_growth_rate"] = "slow"

    # Storytelling frequency: avg open stories per snapshot
    if sessions:
        avg_stories = sum(s["num_stories"] for s in sessions) / len(sessions)
        if avg_stories > 2:
            rhythm["storytelling_frequency"] = "high"
        elif avg_stories > 0.5:
            rhythm["storytelling_frequency"] = "moderate"
        else:
            rhythm["storytelling_frequency"] = "low"

    _save(rhythm)
    return rhythm


def get_rhythm() -> dict:
    return _load()


def get_rhythm_hint() -> str:
    """Brief hint for the scaffold about user's current context."""
    rhythm = _load()
    now_hour = datetime.utcnow().hour
    if 22 <= now_hour or now_hour < 2:
        return f"late night — user tends to be: {rhythm.get('most_open_time', 'unknown')} then"
    return ""
