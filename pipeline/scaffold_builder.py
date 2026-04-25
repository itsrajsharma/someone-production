"""
Scaffold Builder
Compresses all 4 pipeline layers into a ~60-80 token prompt scaffold
that the model receives before the user message.

All callers now pass user_id + session_id + persona. No file I/O.
"""

from datetime import datetime, timezone

from .dependency_resolver import resolve_dependencies
from .tension_detector import get_top_open_loop
from .ebf_engine import get_ebf_summary, get_respond_directive
from .open_stories import check_reactivation
from .snapshot_engine import get_accumulated_facts
from .turn_store import get_all_turns, get_session_facts, extract_tags

# A gap larger than this between turns = new session
_SESSION_GAP_MINUTES = 30


def _get_current_session_turns(all_turns: list) -> list:
    """
    Walk backwards through turns and collect the continuous block
    that belongs to the current session (no gap > _SESSION_GAP_MINUTES).
    Returns turns in chronological order.
    """
    if not all_turns:
        return []

    def _parse_ts(t: dict):
        ts = t.get("timestamp", "")
        try:
            return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        except Exception:
            return None

    session = [all_turns[-1]]
    for i in range(len(all_turns) - 2, -1, -1):
        t_newer = _parse_ts(all_turns[i + 1])
        t_older = _parse_ts(all_turns[i])
        if t_newer is None or t_older is None:
            break
        gap_minutes = (t_newer - t_older).total_seconds() / 60
        if gap_minutes > _SESSION_GAP_MINUTES:
            break
        session.insert(0, all_turns[i])

    return session


def _compress(text: str, max_chars: int) -> str:
    """Hard truncate to approximate token budget (1 token ≈ 4 chars)."""
    return text[:max_chars].strip()


def build_scaffold(
    user_message: str,
    user_id: str,
    session_id: str,
    persona: str = "aria",
) -> str:
    """
    Build the full scaffold prompt for the current user message.
    Returns the scaffold string to prepend before USER: {message}.
    """

    # — CONTEXT: what's being discussed (current session only) —
    all_turns = get_all_turns(user_id, persona)
    session_turns = _get_current_session_turns(all_turns)
    recent_turns = session_turns[-6:] if len(session_turns) >= 6 else session_turns

    from .identity_engine import get_core_identity
    identity = get_core_identity(user_id)
    psycho_profile = identity.get("psychological_profile", "")
    chapter = identity.get("current_life_chapter", "")
    traits = identity.get("enduring_traits", [])

    identity_line = ""
    if psycho_profile and psycho_profile != "No profile exists yet.":
        identity_line = (
            f"PSYCHOLOGICAL PROFILE: {psycho_profile}\n"
            f"CURRENT CHAPTER: {chapter}\n"
            f"ENDURING TRAITS: {', '.join(traits)}\n"
        )

    # Older relevant memory — causal search across ALL turns, excluding current session
    relevant_turns = resolve_dependencies(user_message, user_id, persona, top_k=6)
    older_memory = [t for t in relevant_turns if t not in session_turns]

    if recent_turns:
        context_parts = [f"{t['role'].upper()}: {t['content']}" for t in recent_turns]
        context = " | ".join(context_parts)
    else:
        context = "first message in session"

    memory_line = ""
    if older_memory:
        mem_parts = [f"{t['role'].upper()}: {t['content']}" for t in older_memory]
        memory_line = f"OLDER MEMORY (past session): {' | '.join(mem_parts)}\n"

    # — LAST DECISION: most recent bot message —
    bot_turns = [t for t in all_turns if t["role"] == "assistant"]
    last_decision = bot_turns[-1]["content"] if bot_turns else "no prior response"

    # — CURRENT INTENT —
    intent_map = {
        "question": "seeking an answer or validation",
        "statement": "sharing or venting",
    }
    current_tags = extract_tags(user_message)
    intent = intent_map.get(current_tags.get("intent", "statement"), "sharing")
    if current_tags.get("has_goal"):
        intent = "expressing a goal or desire"

    # — KNOWN FACTS from long-term memory —
    facts = get_accumulated_facts(user_id, persona)
    facts_line = ""
    if facts:
        facts_line = "RECENT KNOWN FACTS: " + ", ".join(facts[-15:]) + "\n"

    session_facts = get_session_facts(user_id, session_id, persona)
    session_line = ""
    if session_facts:
        session_line = "SESSION KNOWN: " + " | ".join(session_facts) + "\n"

    # — OPEN LOOP: most recent unresolved tension —
    open_loop = get_top_open_loop(user_id, persona)
    open_loop_line = f"OPEN LOOP: {open_loop}\n" if open_loop else ""

    # — OPEN STORY REACTIVATION —
    reactivated_story = check_reactivation(user_message, user_id, persona)
    story_line = ""
    if reactivated_story:
        story_line = (
            f"MEMORY: relates to '{reactivated_story['title']}' "
            f"— {_compress(reactivated_story['summary'], 50)}\n"
        )

    # — EMOTIONAL STATE from EBF —
    emotional_state = get_ebf_summary(user_id, persona)

    # — RESPOND directive from EBF —
    respond = get_respond_directive(user_id, persona)

    # — HEALTH CONTEXT (only when user is asking about health/stats) —
    health_line = ""
    _HEALTH_KEYWORDS = {
        "health", "sleep", "stress", "data", "week", "report",
        "synced", "update", "heart", "steps", "trend", "anomaly",
        "workout", "fitness", "wellbeing", "tired", "exhausted",
    }
    _msg_lower = user_message.lower()
    _health_relevant = any(kw in _msg_lower for kw in _HEALTH_KEYWORDS)

    if _health_relevant:
        from db.client import get_db
        db = get_db()
        hr_result = (
            db.table("health_reports")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if hr_result.data:
            hr = hr_result.data[0]
            ws = hr.get("week_summary", {})
            anoms = hr.get("anomalies", [])
            h_parts = [
                f"HEALTH: sleep avg {ws.get('avg_sleep', 0)}hr, "
                f"stress avg {ws.get('avg_stress', 0)}, trend {ws.get('trend', 'stable')}"
            ]
            for a in anoms:
                h_parts.append(f"ANOMALY: {a.get('day')} — {a.get('reason')}")
            comp = hr.get("compared_to_last_week")
            if comp:
                h_parts.append(
                    f"VS LAST WEEK: sleep {comp.get('change_sleep', 0):+.1f}hr, "
                    f"stress {comp.get('change_stress', 0):+.1f}"
                )
            health_line = "\n".join(h_parts) + "\n"

    if not _health_relevant:
        health_suppress = "RULE: User has NOT asked about health. Do NOT mention sleep, stress, heart rate, or any health stats in your response.\n"
    else:
        health_suppress = ""

    # ── Assemble Scaffold ─────────────────────────────────────────────────────
    scaffold = (
        f"{identity_line}"
        f"CONTEXT: {context}\n"
        f"LAST DECISION: {last_decision}\n"
        f"CURRENT INTENT: {intent}\n"
        f"{memory_line}"
        f"{facts_line}"
        f"{session_line}"
        f"{open_loop_line}"
        f"{story_line}"
        f"{health_line}"
        f"{health_suppress}"
        f"EMOTIONAL STATE: {emotional_state}\n"
        f"RESPOND: {respond}\n"
    )

    return scaffold.strip()
