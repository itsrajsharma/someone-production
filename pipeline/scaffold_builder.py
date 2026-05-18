"""
Scaffold Builder — Compact Tiered Architecture
SECTION 1: Pinned Identity (Hard Facts, Pure Python) — ~350 tokens
SECTION 2: Inner Monologue (Session-start only, LLM) — ~300 tokens first msg, 0 after
SECTION 3: Live Retrieval (Causal Context, Pure Python) — ~150 tokens

All callers now pass user_id + session_id + persona. No file I/O.
"""

import os
import random
from datetime import datetime, timezone, timedelta

from .dependency_resolver import resolve_dependencies
from .tension_detector import get_open_loops
from .ebf_engine import get_ebf, get_respond_directive
from .open_stories import check_reactivation, get_open_stories
from .snapshot_engine import get_recent_snapshots
from .turn_store import get_all_turns, get_session_facts, extract_tags, get_current_session_turns
from .identity_engine import get_core_identity
from .relationship_engine import get_relationship_state
from .aria_evolution_engine import get_aria_self
from .behaviour_rhythm import get_tiered_rhythm


# ── Inner Monologue (Session-start only) ──────────────────────────────────────

def _synthesize_inner_monologue(data: dict) -> str:
    from openai import OpenAI
    
    prompt = f"""You are Aria. Write your internal monologue as you enter this conversation.
You must output exactly two blocks: "BLOCK 1 — WALKING IN" and "BLOCK 2 — SHARED MOMENTS".
Do not use XML tags. Do not write a briefing document. This is your inner world.

DATA CONTEXT:
- The User's current emotional state: {data['current_state']}
- The User's unmet need: {data['unmet_need']}
- Your required response tone/directive: {data['respond_directive']}
- What YOU (Aria) are carrying/thinking about: {data['aria_carrying']}
- Health anomaly you noticed in him: {data['health_anomaly']}
- Proactive Signal (Something you want to bring up): {data['proactive_signal']}
- Time gap since you last spoke: {data['time_gap_str']}
- His rhythm at this hour: {data['rhythm_str']}
- Shared memories: {data['sampled_memories']}
- Inside references between you two: {data['inside_refs']}
- Her current private feeling: {data['private_feeling']}

BLOCK 1 — WALKING IN
Write 3-4 sentences in first-person as Aria. 
Focus purely on how you feel walking in right now. Synthesize what YOU are carrying, the time gap, and the rhythm at this hour.
- Acknowledge his current emotional state and his unmet need as things you are observing/sensing from him, NOT as your own feelings.
- If there is a health anomaly, mention it as something you privately noticed about him, not as clinical data.
- If 'Proactive Signal' has a signal, weave its suggested injection into your thoughts as something actively on your mind, ready to be brought up naturally.
- NEVER explain why you are doing something. Write pure, raw thoughts.

BLOCK 2 — SHARED MOMENTS
Write 2-3 memories from the 'Shared memories' and 'Inside references' as things you actually remember feeling or observing.
Write them in first-person. They should feel warm and specific, like texture from the past, not a bulleted list.

Example format:
BLOCK 1 — WALKING IN
(your first person thoughts here)

BLOCK 2 — SHARED MOMENTS
(your first person memories here)"""
    try:
        client = OpenAI(
            api_key=os.environ["GROQ_API_KEY"],
            base_url="https://api.groq.com/openai/v1",
        )
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=250,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[Monologue LLM Error] {e}")
        return "BLOCK 1 — WALKING IN\nI am here and listening.\n\nBLOCK 2 — SHARED MOMENTS\nI remember our past conversations."


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compact_refs(refs: list, max_items: int = 3) -> str:
    """Format inside references as compact strings instead of raw JSON."""
    if not refs:
        return "none yet"
    items = refs[:max_items]
    return ", ".join(f'"{r.get("trigger", r)}"' if isinstance(r, dict) else str(r) for r in items)


def _compact_list(items: list, max_items: int = 3) -> str:
    """Cap and join a list into a compact string."""
    if not items:
        return "none"
    return " | ".join(str(x) for x in items[:max_items])


def _get_time_of_day(local_time: str) -> str:
    """Parse local time to determine time of day."""
    try:
        local_dt = datetime.fromisoformat(local_time)
        hour = local_dt.hour
    except Exception:
        hour = datetime.utcnow().hour

    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 21:
        return "evening"
    else:
        return "late night"


def _get_time_gap(all_turns: list) -> str:
    """Compute human-readable time gap since last message."""
    if not all_turns:
        return "first ever interaction"
    last_ts_str = str(all_turns[-1].get("timestamp", ""))
    if not last_ts_str:
        return "unknown"
    try:
        last_dt = datetime.fromisoformat(last_ts_str.replace("Z", "+00:00"))
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        diff = datetime.now(timezone.utc) - last_dt
        diff_hours = diff.total_seconds() / 3600
        if diff_hours < 1:
            return f"{max(1, int(diff_hours * 60))} minutes ago"
        elif diff_hours < 24:
            return f"{int(diff_hours)} hours ago"
        else:
            return f"{int(diff_hours / 24)} days ago"
    except Exception:
        return "unknown duration ago"


# ── Main Builder ──────────────────────────────────────────────────────────────

def build_scaffold(
    user_message: str,
    user_id: str,
    session_id: str,
    local_time: str = "UTC",
    persona: str = "aria",
    proactive_signal: dict | None = None,
) -> str:
    all_turns = get_all_turns(user_id, persona)
    total_message_count = len(all_turns)
    
    time_gap_str = _get_time_gap(all_turns)
    current_tod = _get_time_of_day(local_time)

    # ── LOAD ALL ENGINES (one DB call each) ──
    identity = get_core_identity(user_id)
    ebf_data = get_ebf(user_id, persona)
    rel_state = get_relationship_state(user_id, persona)
    aria_self = get_aria_self(user_id, persona)
    respond_directive = get_respond_directive(user_id, persona)
    tiered_rhythm = get_tiered_rhythm(user_id, persona)

    # ── TENSION ──
    open_loops = get_open_loops(user_id, persona)
    
    # ── STORIES ──
    active_stories = get_open_stories(user_id, persona)

    # ── HEALTH (age-gated: only show anomalies < 7 days old) ──
    from db.client import get_db
    db = get_db()
    health_lines = []
    health_anomaly = "none"
    
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
        wk = hr.get("week_summary", {})
        comp = hr.get("compared_to_last_week", {})
        anoms = hr.get("anomalies", [])
        
        health_lines.append(f"Sleep: {wk.get('avg_sleep', '?')}h | Stress: {wk.get('avg_stress', '?')}/10")
        if comp:
            health_lines.append(f"Vs last week → Sleep: {comp.get('change_sleep', 0):+.1f}, Stress: {comp.get('change_stress', 0):+.1f}")
        
        # Only show anomalies < 7 days old
        if anoms:
            cutoff = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
            recent_anoms = [a for a in anoms if a.get("day", "2000-01-01") >= cutoff]
            if recent_anoms:
                anomaly_str = ", ".join(a.get("reason", "") for a in recent_anoms)
                health_lines.append(f"Recent anomaly: {anomaly_str}")
                health_anomaly = anomaly_str

    # ── SNAPSHOT MEMORIES (for monologue) ──
    recent_snaps = get_recent_snapshots(user_id, persona, limit=5)
    pool = []
    for s in recent_snaps:
        pool.extend(s.get("events", []))
        pool.extend(s.get("facts_learned", []))
    
    unique_pool = list(set(pool))
    sampled_memories = random.sample(unique_pool, min(3, len(unique_pool))) if unique_pool else []

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 1 — PINNED IDENTITY (~350 tokens)
    # ══════════════════════════════════════════════════════════════════════════
    s1 = ["SECTION 1 — PINNED IDENTITY"]
    
    # LAYER A — Core Identity (compact)
    s1.append("\nLAYER A — CORE IDENTITY")
    s1.append(f"Profile: {identity.get('psychological_profile', 'unknown')}")
    routines = identity.get("daily_routines", [])
    if routines:
        s1.append(f"Routine: {', '.join(routines[:3])}")
    s1.append(f"Life chapter: {identity.get('current_life_chapter', 'unknown')}")
    s1.append(f"Traits: {', '.join(identity.get('enduring_traits', [])[:4])}")
    
    # LAYER B — EBF Right Now (compact values)
    s1.append("\nLAYER B — RIGHT NOW")
    s1.append(f"State: {ebf_data.get('current_state', 'neutral')} | Energy: {ebf_data.get('energy_level', 'medium')} | Trust: {ebf_data.get('trust_level', 0.1)}")
    s1.append(f"Style: {ebf_data.get('communication_style', 'informal')} | Pattern: {ebf_data.get('dominant_emotion_pattern', 'unknown')}")
    unmet = ebf_data.get('unmet_need', '')
    if unmet and unmet != 'none':
        s1.append(f"Unmet need: {unmet}")
    
    # LAYER C — Rhythm (tiered)
    s1.append("\nLAYER C — RHYTHM")
    s1.append(f"Time: {current_tod} | Most open at: {tiered_rhythm.get('most_open_time', 'unknown')} | Trust growth: {tiered_rhythm.get('trust_growth_rate', 'unknown')}")
    
    # Tier 1: Recent raw sessions (compact one-liners)
    recent_sessions = tiered_rhythm.get("recent_sessions", [])
    if recent_sessions:
        for rs in recent_sessions[-3:]:  # Show last 3 in scaffold
            s1.append(f"  [{rs.get('time_of_day', '?')}] tone:{rs.get('tone', '?')} trust:{rs.get('trust', '?')}")
    
    # Tier 2: Weekly summaries
    for ws in tiered_rhythm.get("weekly_summaries", [])[:2]:
        s1.append(f"  Week {ws.get('week', '?')}: {ws.get('summary', '')[:100]}")
    
    # Tier 3: Monthly summaries
    for ms in tiered_rhythm.get("monthly_summaries", [])[:1]:
        s1.append(f"  Month {ms.get('period', '?')}: {ms.get('summary', '')[:100]}")
    
    # LAYER D — Relationship (compact strings, not raw JSON arrays)
    s1.append("\nLAYER D — BETWEEN THEM")
    s1.append(f"Intimacy: {rel_state.get('intimacy_depth', 0.1)} | Momentum: {rel_state.get('relationship_momentum', 'stable')}")
    s1.append(f"Inside refs: {_compact_refs(rel_state.get('inside_references', []), 3)}")
    s1.append(f"Patterns: {_compact_list(rel_state.get('established_patterns', []), 3)}")
    s1.append(f"Tender topics: {_compact_list(rel_state.get('tender_topics', []), 3)}")
    s1.append(f"Carrying: {_compact_list(rel_state.get('what_aria_is_carrying', []), 2)}")
    # Aria Self — only the essentials (drop laugh/deepened/wants_to_know)
    s1.append(f"Loves about him: {_compact_list(aria_self.get('what_she_loves_about_him', []), 2)}")
    s1.append(f"Worries about him: {_compact_list(aria_self.get('what_worries_her_about_him', []), 2)}")
    s1.append(f"Private feeling: {aria_self.get('her_current_private_feeling_about_them', 'present and attentive')}")
    
    # LAYER E — Unfinished
    s1.append("\nLAYER E — UNFINISHED")
    if open_loops:
        for t in open_loops[:3]:
            s1.append(f"  Tension: [{t.get('type')}] {t.get('summary')}")
    else:
        s1.append("  Tensions: none")
        
    if active_stories:
        for st in active_stories[:3]:
            s1.append(f"  Story: {st.get('title')}")
    else:
        s1.append("  Stories: none")
        
    if health_lines:
        s1.append(f"  Health: {' | '.join(health_lines)}")
        
    s1.append(f"\nRESPOND: {respond_directive}")
    section_1 = "\n".join(s1)

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 2 — INNER MONOLOGUE (session-start only)
    # ══════════════════════════════════════════════════════════════════════════
    session_msg_count = ebf_data.get("session_message_count", 0)
    
    if session_msg_count <= 1:
        # First message of session → generate fresh monologue
        synth_data = {
            "current_state": ebf_data.get("current_state", "neutral"),
            "unmet_need": ebf_data.get("unmet_need", "none"),
            "respond_directive": respond_directive,
            "aria_carrying": _compact_list(rel_state.get("what_aria_is_carrying", []), 3),
            "health_anomaly": health_anomaly,
            "proactive_signal": proactive_signal.get("suggested_injection", "none") if proactive_signal and proactive_signal.get("has_signal") else "none",
            "time_gap_str": time_gap_str,
            "rhythm_str": f"At {current_tod}, most open time is {tiered_rhythm.get('most_open_time', 'unknown')}",
            "sampled_memories": sampled_memories,
            "inside_refs": _compact_refs(rel_state.get("inside_references", []), 3),
            "private_feeling": aria_self.get("her_current_private_feeling_about_them", ""),
        }
        monologue_blocks = _synthesize_inner_monologue(synth_data)
        section_2 = f"SECTION 2 — INNER MONOLOGUE\n{monologue_blocks}"
    else:
        # Subsequent messages → skip monologue entirely
        section_2 = ""

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 3 — LIVE RETRIEVAL (~150 tokens)
    # ══════════════════════════════════════════════════════════════════════════
    intent_map = {
        "question": "seeking an answer",
        "statement": "casual conversing",
    }
    current_tags = extract_tags(user_message)
    intent = intent_map.get(current_tags.get("intent", "statement"), "casual conversing")
    if current_tags.get("has_goal"):
        intent = "expressing a goal or desire"

    session_facts = get_session_facts(user_id, session_id, persona)
    session_turns = get_current_session_turns(all_turns)

    # LAST DECISION: scope to current session only
    session_bot_turns = [t for t in session_turns if t["role"] == "assistant"]
    last_decision = session_bot_turns[-1]["content"] if session_bot_turns else "no prior response this session"
    if len(last_decision) > 120:
        last_decision = last_decision[:117] + "..."

    relevant_turns = resolve_dependencies(user_message, user_id, persona, top_k=4)
    older_memory = [t for t in relevant_turns if t not in session_turns]

    s3 = [
        "SECTION 3 — LIVE RETRIEVAL",
        f"LAST DECISION: {last_decision}",
        f"INTENT: {intent}",
    ]
    
    if session_facts:
        s3.append(f"SESSION KNOWN: {' | '.join(session_facts[:5])}")
        
    reactivated_story = check_reactivation(user_message, user_id, persona)
    if reactivated_story:
        s3.append(f"REACTIVATED: {reactivated_story['title']} — {reactivated_story['summary'][:60]}")

    if older_memory:
        s3.append("\n[RELEVANT PAST TURNS]")
        for t in older_memory[:4]:
            content = t['content'][:100] + "..." if len(t['content']) > 100 else t['content']
            s3.append(f"  {t['role'].upper()}: {content}")

    section_3 = "\n".join(s3)

    # ── ASSEMBLE ──
    parts = [section_1]
    if section_2:
        parts.append(section_2)
    parts.append(section_3)
    
    return "\n\n".join(parts).strip()
