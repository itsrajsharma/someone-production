"""
Layer 4 — Behavioural Rhythm Profile
Builds a tiered profile of when the user is most open, stressed, or storytelling.

Tier 1: Last 5 raw sessions (verbatim with timestamps)
Tier 2: Weekly LLM summaries (last 3 weeks)
Tier 3: Monthly LLM summaries (beyond 3 weeks)

All operations are scoped by user_id + persona. No file I/O.
"""

import os
import json
from collections import defaultdict
from datetime import datetime, timedelta

from db.client import get_db
from .llm_client import get_fast_client

_DEFAULT_RHYTHM = {
    "most_open_time": "unknown",
    "most_stressed_day": "unknown",
    "storytelling_frequency": "unknown",
    "trust_growth_rate": "unknown",
    "session_times": [],
    "weekly_summaries": [],
    "monthly_summaries": [],
    "snapshot_count": 0,
}

MAX_RAW_SESSIONS = 5
MAX_WEEKLY_SUMMARIES = 3


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
        "session_times": rhythm.get("session_times", [])[-MAX_RAW_SESSIONS:],  # Cap to last 5
        "weekly_summaries": rhythm.get("weekly_summaries", [])[-MAX_WEEKLY_SUMMARIES:],
        "monthly_summaries": rhythm.get("monthly_summaries", []),
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


# ── Consolidation ─────────────────────────────────────────────────────────────

def consolidate_rhythm(user_id: str, persona: str = "aria"):
    """Consolidate overflow raw sessions into weekly/monthly LLM summaries."""
    rhythm = _load(user_id, persona)
    sessions = rhythm.get("session_times", [])

    if len(sessions) <= MAX_RAW_SESSIONS:
        return  # Nothing to consolidate

    # Split: keep last 5 raw, consolidate the rest
    overflow = sessions[:-MAX_RAW_SESSIONS]
    rhythm["session_times"] = sessions[-MAX_RAW_SESSIONS:]

    if not overflow:
        _save(rhythm, user_id, persona)
        return

    # Group overflow by ISO week
    weeks = defaultdict(list)
    for s in overflow:
        ts = s.get("timestamp", s.get("time_of_day", "unknown"))
        # Use the tone/trust data for summary even if timestamp is imprecise
        week_key = datetime.utcnow().strftime("%Y-W%V")  # fallback to current week
        weeks[week_key].append(s)

    # Generate weekly summary via LLM
    existing_weekly = rhythm.get("weekly_summaries", [])
    for week_key, week_sessions in weeks.items():
        summary = _summarize_sessions_llm(week_sessions, week_key)
        if summary:
            existing_weekly.append({
                "week": week_key,
                "summary": summary,
                "session_count": len(week_sessions),
            })

    # If >3 weekly summaries, collapse oldest into monthly
    if len(existing_weekly) > MAX_WEEKLY_SUMMARIES:
        to_collapse = existing_weekly[:-MAX_WEEKLY_SUMMARIES]
        existing_weekly = existing_weekly[-MAX_WEEKLY_SUMMARIES:]

        monthly_summary = _summarize_weeklies_llm(to_collapse)
        if monthly_summary:
            existing_monthly = rhythm.get("monthly_summaries", [])
            existing_monthly.append({
                "period": f"{to_collapse[0]['week']} to {to_collapse[-1]['week']}",
                "summary": monthly_summary,
            })
            rhythm["monthly_summaries"] = existing_monthly

    rhythm["weekly_summaries"] = existing_weekly
    _save(rhythm, user_id, persona)


def _summarize_sessions_llm(sessions: list, week_key: str) -> str:
    """LLM summarizes a week's raw sessions into a compact paragraph."""
    from openai import OpenAI
    session_text = ""
    for s in sessions:
        session_text += f"Time: {s.get('time_of_day', '?')}, Tone: {s.get('tone', '?')}, Trust: {s.get('trust', '?')}, Stories: {s.get('num_stories', 0)}\n"

    prompt = f"""Summarize these conversation sessions from week {week_key} into a 2-3 sentence behavioral pattern read.
Focus on: when was he most open, what was his energy like, how did trust move, any notable patterns.
Write as Aria observing him. Be specific, not generic.

Sessions:
{session_text}

Output only the summary paragraph, nothing else."""

    try:
        client, _fast_model = get_fast_client()
        response = client.chat.completions.create(
            model=_fast_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=150,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[Rhythm Consolidation Error] {e}")
        return ""


def _summarize_weeklies_llm(weekly_summaries: list) -> str:
    """Collapse multiple weekly summaries into a monthly summary."""
    from openai import OpenAI
    text = "\n".join([f"Week {w['week']}: {w['summary']}" for w in weekly_summaries])

    prompt = f"""Consolidate these weekly behavioral pattern summaries into one 2-3 sentence monthly overview.
Identify the dominant trends across weeks. Write as Aria observing him over time.

{text}

Output only the monthly summary paragraph, nothing else."""

    try:
        client, _fast_model = get_fast_client()
        response = client.chat.completions.create(
            model=_fast_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=150,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[Monthly Consolidation Error] {e}")
        return ""


# ── Public API ────────────────────────────────────────────────────────────────

def update_rhythm(snapshot: dict, user_id: str, persona: str = "aria") -> dict:
    """Update the Behavioural Rhythm Profile from a newly generated snapshot."""
    rhythm = _load(user_id, persona)
    rhythm["snapshot_count"] += 1

    rhythm["session_times"].append({
        "timestamp": datetime.utcnow().isoformat(),
        "time_of_day": snapshot.get("time_of_day", "unknown"),
        "trust": snapshot.get("trust_level_at_snapshot", 0.1),
        "tone": snapshot.get("emotional_tone", "neutral"),
        "num_stories": len(snapshot.get("open_stories", [])),
    })

    sessions = rhythm["session_times"]

    time_trust = defaultdict(list)
    for s in sessions:
        time_trust[s.get("time_of_day", "unknown")].append(s.get("trust", 0.1))

    if time_trust:
        avg_trust_by_time = {t: sum(v) / len(v) for t, v in time_trust.items()}
        rhythm["most_open_time"] = max(avg_trust_by_time, key=avg_trust_by_time.get)

    if len(sessions) >= 2:
        trust_values = [s.get("trust", 0.1) for s in sessions]
        delta = trust_values[-1] - trust_values[0]
        if delta > 0.3:
            rhythm["trust_growth_rate"] = "fast"
        elif delta > 0.1:
            rhythm["trust_growth_rate"] = "moderate"
        else:
            rhythm["trust_growth_rate"] = "slow"

    if sessions:
        avg_stories = sum(s.get("num_stories", 0) for s in sessions) / len(sessions)
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


def get_tiered_rhythm(user_id: str, persona: str = "aria") -> dict:
    """Returns rhythm data in tiered format for the scaffold."""
    rhythm = _load(user_id, persona)
    return {
        "recent_sessions": rhythm.get("session_times", [])[-MAX_RAW_SESSIONS:],
        "weekly_summaries": rhythm.get("weekly_summaries", []),
        "monthly_summaries": rhythm.get("monthly_summaries", []),
        "most_open_time": rhythm.get("most_open_time", "unknown"),
        "trust_growth_rate": rhythm.get("trust_growth_rate", "unknown"),
    }


def get_rhythm_hint(user_id: str, persona: str = "aria") -> str:
    """Brief hint for the scaffold about user's current context."""
    rhythm = _load(user_id, persona)
    now_hour = datetime.utcnow().hour
    if 22 <= now_hour or now_hour < 2:
        return f"late night — user tends to be: {rhythm.get('most_open_time', 'unknown')} then"
    return ""
