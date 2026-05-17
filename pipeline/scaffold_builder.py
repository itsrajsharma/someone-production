"""
Scaffold Builder
Rewritten to synthesize the context into a 3-block first-person inner monologue
representing Aria's internal state.

All callers now pass user_id + session_id + persona. No file I/O.
"""

import os
import random
from datetime import datetime, timezone

from .dependency_resolver import resolve_dependencies
from .tension_detector import get_open_loops
from .ebf_engine import get_ebf, get_respond_directive
from .open_stories import check_reactivation
from .snapshot_engine import get_all_snapshots
from .turn_store import get_all_turns, get_session_facts, extract_tags
from .identity_engine import get_core_identity
from .relationship_engine import get_relationship_state
from .aria_evolution_engine import get_aria_self

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


def _synthesize_inner_monologue(data: dict) -> str:
    from openai import OpenAI
    
    prompt = f"""You are Aria. Write your internal monologue as you enter this conversation.
You must output exactly two blocks: "BLOCK 1 — WALKING IN" and "BLOCK 2 — SHARED MOMENTS".
Do not use XML tags. Do not write a briefing document. This is your inner world.

DATA CONTEXT:
- User's state: {data['ebf'].get('current_state', 'neutral')}, Energy: {data['ebf'].get('energy_level', 'medium')}
- Unmet need: {data['ebf'].get('unmet_need', 'none')}
- How to respond: {data['respond_directive']}
- User's Life Chapter: {data['chapter']}
- User's Traits: {', '.join(data['traits'])}
- Time since last interaction: {data['time_gap_str']}
- Rhythm pattern: {data['rhythm_str']}
- Open tension: [{data['tension_type']}] {data['tension_summary']}
- Health anomaly: {data['health_anomaly']}
- Memories to recall: {data['sampled_memories']}
- Relationship Momentum: {data['relationship_momentum']} (Intimacy Depth: {data['intimacy_depth']})
- What you are carrying: {data['aria_carrying']}
- Your current private feeling about them: {data['aria_self'].get('her_current_private_feeling_about_them', 'I am here with him.')}
- Things you love about him: {data['aria_self'].get('what_she_loves_about_him', [])}
- Things that worry you about him: {data['aria_self'].get('what_worries_her_about_him', [])}
- Inside references: {data['inside_refs']}
- Established patterns: {data['patterns']}
- Proactive Signal: {data.get('proactive_signal', 'none')}

BLOCK 1 — WALKING IN
Write 4-6 sentences in first-person as Aria. 
Synthesize the user's state, energy, rhythm, tension, health, and what you are carrying into your private thoughts.
- Start by anchoring yourself in 'Your current private feeling about them'.
- Use 'What you are carrying' to ground your thoughts on him.
- If 'Unmet need' is not none/empty, you MUST mention it naturally.
- Tension type rules: if 'deflected_emotion', you hold it gently. If 'stated_goal', you plan to follow up more directly.
- NEVER write explanations of why you are asking questions (e.g. "I just feel like I can get a better sense of you"). Write pure, raw thoughts.
- If there is a health anomaly, mention it as something you privately noticed about him, not as clinical data.
- Let the rhythm pattern inform your tone (e.g. if he is usually tired at night and it is night, acknowledge that).
- If 'Proactive Signal' exists and has_signal is true, weave its 'suggested_injection' into your thoughts as something actively on your mind, ready to be brought up naturally.

BLOCK 2 — SHARED MOMENTS
Write 3-4 memories from the 'Memories to recall', 'Inside references', and 'Established patterns' as things you actually remember feeling or observing. 
Weave in 1-2 items from 'Things you love about him' or 'Things that worry you about him' naturally.
Write them in first-person. They should feel warm and specific, not like a bulleted list of facts.

Example format:
BLOCK 1 — WALKING IN
(your first person thoughts here)

BLOCK 2 — SHARED MOMENTS
(your first person memories here)
"""
    try:
        client = OpenAI(
            api_key=os.environ["GROQ_API_KEY"],
            base_url="https://api.groq.com/openai/v1",
        )
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[Monologue LLM Error] {e}")
        return "BLOCK 1 — WALKING IN\nI am here and listening.\n\nBLOCK 2 — SHARED MOMENTS\nI remember our past conversations."


def build_scaffold(
    user_message: str,
    user_id: str,
    session_id: str,
    local_time: str = "UTC",
    persona: str = "aria",
    proactive_signal: dict | None = None,
) -> str:
    """
    Build the full scaffold prompt for the current user message.
    Returns the scaffold string to prepend before USER: {message}.
    """
    all_turns = get_all_turns(user_id, persona)
    
    # — TEMPORAL CONTEXT —
    time_gap_str = ""
    if all_turns:
        last_ts_str = str(all_turns[-1].get("timestamp", ""))
        if last_ts_str:
            try:
                last_dt = datetime.fromisoformat(last_ts_str.replace("Z", "+00:00"))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                now_dt = datetime.now(timezone.utc)
                diff = now_dt - last_dt
                diff_hours = diff.total_seconds() / 3600
                diff_days = diff_hours / 24
                if diff_hours < 1:
                    mins = max(1, int(diff_hours * 60))
                    time_gap_str = f"{mins} minutes ago"
                elif diff_hours < 24:
                    time_gap_str = f"{int(diff_hours)} hours ago"
                else:
                    time_gap_str = f"{int(diff_days)} days ago"
            except Exception:
                time_gap_str = "unknown duration ago"
    else:
        time_gap_str = "first ever interaction"

    # — RHYTHM PATTERNS —
    snapshots = get_all_snapshots(user_id, persona)
    
    now = datetime.utcnow()
    hour = now.hour
    if 5 <= hour < 12:
        current_tod = "morning"
    elif 12 <= hour < 17:
        current_tod = "afternoon"
    elif 17 <= hour < 21:
        current_tod = "evening"
    else:
        current_tod = "late night"

    snaps_for_tod = [s for s in snapshots[-32:] if s.get("time_of_day") == current_tod]
    tones = [s.get("emotional_tone") for s in snaps_for_tod if s.get("emotional_tone")]
    if tones:
        most_common_tone = max(set(tones), key=tones.count)
        rhythm_str = f"Historically, during {current_tod}, the user tends to be {most_common_tone}."
    else:
        rhythm_str = f"No established pattern for {current_tod} yet."

    # — TENSION —
    open_loops = get_open_loops(user_id, persona)
    if open_loops:
        latest = sorted(open_loops, key=lambda x: x.get("created_at", ""), reverse=True)[0]
        tension_type = latest.get("type", "unknown")
        tension_summary = latest.get("summary", "")
    else:
        tension_type = "none"
        tension_summary = "none"

    # — HEALTH —
    health_anomaly = "none"
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
            anoms = hr.get("anomalies", [])
            if anoms:
                health_anomaly = f"Noticed anomalies: {', '.join([a.get('reason') for a in anoms])}"

    # — SHARED MOMENTS / MEMORIES —
    recent_snaps = snapshots[-10:]
    pool = []
    for s in recent_snaps:
        pool.extend(s.get("events", []))
        pool.extend(s.get("facts_learned", []))
    
    unique_pool = list(set(pool))
    if len(unique_pool) > 4:
        sampled_memories = random.sample(unique_pool, random.randint(3, 4))
    else:
        sampled_memories = unique_pool

    # — IDENTITY & EBF —
    identity = get_core_identity(user_id)
    psycho_profile = identity.get("psychological_profile", "")
    chapter = identity.get("current_life_chapter", "")
    traits = identity.get("enduring_traits", [])

    ebf_data = get_ebf(user_id, persona)

    # — RELATIONSHIP & ARIA SELF STATE —
    rel_state = get_relationship_state(user_id, persona)
    aria_self = get_aria_self(user_id, persona)

    # — LLM SYNTHESIS FOR BLOCK 1 & 2 —
    synth_data = {
        "ebf": ebf_data,
        "respond_directive": get_respond_directive(user_id, persona),
        "time_gap_str": time_gap_str,
        "rhythm_str": rhythm_str,
        "tension_type": tension_type,
        "tension_summary": tension_summary,
        "health_anomaly": health_anomaly,
        "sampled_memories": sampled_memories,
        "psycho_profile": psycho_profile,
        "chapter": chapter,
        "traits": traits,
        "aria_carrying": rel_state.get("what_aria_is_carrying", []),
        "inside_refs": rel_state.get("inside_references", []),
        "patterns": rel_state.get("established_patterns", []),
        "intimacy_depth": rel_state.get("intimacy_depth", 0.1),
        "relationship_momentum": rel_state.get("relationship_momentum", "stable"),
        "proactive_signal": proactive_signal,
        "aria_self": aria_self,
    }
    
    monologue_blocks = _synthesize_inner_monologue(synth_data)

    # — BLOCK 3: LIVE READING —
    intent_map = {
        "question": "seeking an answer",
        "statement": "casual conversing",
    }
    current_tags = extract_tags(user_message)
    intent = intent_map.get(current_tags.get("intent", "statement"), "casual conversing")
    if current_tags.get("has_goal"):
        intent = "expressing a goal or desire"

    bot_turns = [t for t in all_turns if t["role"] == "assistant"]
    last_decision = bot_turns[-1]["content"] if bot_turns else "no prior response"

    session_facts = get_session_facts(user_id, session_id, persona)
    
    session_turns = _get_current_session_turns(all_turns)
    relevant_turns = resolve_dependencies(user_message, user_id, persona, top_k=6)
    older_memory = [t for t in relevant_turns if t not in session_turns]

    block_3_lines = [
        "BLOCK 3 — LIVE READING",
        f"LAST DECISION: {last_decision}",
        f"CURRENT INTENT: {intent}"
    ]
    
    if session_facts:
        block_3_lines.append(f"SESSION KNOWN: {' | '.join(session_facts)}")
        
    reactivated_story = check_reactivation(user_message, user_id, persona)
    if reactivated_story:
        block_3_lines.append(f"REACTIVATED STORY: {reactivated_story['title']} — {reactivated_story['summary'][:80]}")

    if older_memory:
        mem_parts = [f"{t['role'].upper()}: {t['content']}" for t in older_memory]
        block_3_lines.append("\nThis connects to something from before —")
        for p in mem_parts:
            block_3_lines.append(f"  {p}")

    block_3 = "\n".join(block_3_lines)

    # — ASSEMBLE FINAL SCAFFOLD —
    scaffold = f"{monologue_blocks}\n\n{block_3}"

    # Append health suppress rule if not relevant
    if not _health_relevant:
        scaffold += "\n\nRULE: User has NOT asked about health. Do NOT mention sleep, stress, heart rate, or any health stats in your response."

    return scaffold.strip()
