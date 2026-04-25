"""
Oracle Scaffold Builder
Compresses facts, rhythm, health, and tensions into a prompt for Oracle.

All operations are scoped by user_id. No file I/O.
"""

from .tension_detector import get_top_open_loop
from .turn_store import get_session_facts
from db.client import get_db


def build_oracle_scaffold(user_message: str, user_id: str, session_id: str = "") -> str:
    db = get_db()

    # 1. Facts from snapshots
    known = "None"
    snapshot = "None"
    snaps_result = (
        db.table("snapshots")
        .select("facts_learned, events")
        .eq("user_id", user_id)
        .eq("persona", "oracle")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if snaps_result.data:
        row = snaps_result.data[0]
        facts_list = row.get("facts_learned", [])
        events_list = row.get("events", [])
        known = ", ".join(facts_list[:5]) if facts_list else "None"
        snapshot = "; ".join(events_list[:3]) if events_list else "None"

    # 2. Rhythm
    rhythm = "None"
    rhythm_result = (
        db.table("behaviour_rhythm")
        .select("most_open_time, storytelling_frequency, trust_growth_rate")
        .eq("user_id", user_id)
        .eq("persona", "oracle")
        .limit(1)
        .execute()
    )
    if rhythm_result.data:
        row = rhythm_result.data[0]
        most_open = row.get("most_open_time", "unknown")
        freq = row.get("storytelling_frequency", "unknown")
        trust_rate = row.get("trust_growth_rate", "unknown")
        rhythm = f"most open at {most_open}, storytelling={freq}, trust growth={trust_rate}"

    # 3. Health
    health = "None"
    health_result = (
        db.table("health_reports")
        .select("week_summary")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if health_result.data:
        ws = health_result.data[0].get("week_summary", {})
        if ws:
            trend = ws.get("trend", "stable")
            health = f"Avg Sleep: {ws.get('avg_sleep')}, Avg Stress: {ws.get('avg_stress')}, Trend: {trend}"

    # 4. Tensions → Decision Pending
    decision_pending = "None"
    top_loop = get_top_open_loop(user_id, persona="oracle")
    if top_loop:
        decision_pending = top_loop

    session_facts = get_session_facts(user_id, session_id, persona="oracle") if session_id else []
    session_line = ""
    if session_facts:
        session_line = "SESSION KNOWN: " + " | ".join(session_facts) + "\n"

    scaffold = (
        f"KNOWN: {known}\n"
        f"{session_line}"
        f"SNAPSHOT: {snapshot}\n"
        f"RHYTHM: {rhythm}\n"
        f"HEALTH: {health}\n"
        f"DECISION PENDING: {decision_pending}\n"
        f"RESPOND: measured, experienced, see the long arc, no emotional mirroring"
    )

    return scaffold
