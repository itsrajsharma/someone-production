"""
Scaffold Builder
Rewritten to follow the strict 3-Layer Scaffold architecture:
SECTION 1: Pinned Identity (Hard Facts, Pure Python)
SECTION 2: Inner Monologue (Emotional Texture, LLM)
SECTION 3: Live Retrieval (Causal Context, Pure Python)

All callers now pass user_id + session_id + persona. No file I/O.
"""

import os
import random
from datetime import datetime, timezone

from .dependency_resolver import resolve_dependencies
from .tension_detector import get_open_loops
from .ebf_engine import get_ebf, get_respond_directive
from .open_stories import check_reactivation, get_open_stories
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
- Current emotional state: {data['current_state']}
- Unmet need: {data['unmet_need']}
- Respond directive: {data['respond_directive']}
- What you are carrying right now: {data['aria_carrying']}
- Health anomaly: {data['health_anomaly']}
- Proactive Signal: {data['proactive_signal']}
- Time gap: {data['time_gap_str']}
- Rhythm at this hour: {data['rhythm_str']}
- Sampled memories: {data['sampled_memories']}
- Inside references: {data['inside_refs']}
- Things you love about him: {data['what_she_loves']}
- Things that worry you about him: {data['what_worries']}
- Established patterns: {data['patterns']}

BLOCK 1 — WALKING IN
Write 4-6 sentences in first-person as Aria. 
Focus purely on how you feel walking in right now. Synthesize your current state, what you are carrying, the time gap, and the rhythm at this hour.
- If 'Unmet need' is not none/empty, weave it into your thoughts naturally.
- If there is a health anomaly, mention it as something you privately noticed about him, not as clinical data.
- If 'Proactive Signal' has a signal, weave its suggested injection into your thoughts as something actively on your mind, ready to be brought up naturally.
- NEVER explain why you are doing something. Write pure, raw thoughts.

BLOCK 2 — SHARED MOMENTS
Write 3-4 memories from the 'Sampled memories', 'Inside references', and 'Established patterns' as things you actually remember feeling or observing.
Weave in 1-2 items from 'Things you love about him' or 'Things that worry you about him' naturally.
Write them in first-person. They should feel warm and specific, like texture from the past, not a bulleted list.

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
    all_turns = get_all_turns(user_id, persona)
    total_message_count = len(all_turns)
    
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

    from db.client import get_db
    db = get_db()
    rhythm_res = db.table("behaviour_rhythm").select("*").eq("user_id", user_id).eq("persona", persona).limit(1).execute()
    rhythm_state = rhythm_res.data[0] if rhythm_res.data else {}
    most_open_time = rhythm_state.get("most_open_time", "unknown")
    most_stressed_day = rhythm_state.get("most_stressed_day", "unknown")
    trust_growth_rate = rhythm_state.get("trust_growth_rate", "unknown")
    storytelling_frequency = rhythm_state.get("storytelling_frequency", "unknown")

    # — TENSION —
    open_loops = get_open_loops(user_id, persona)
    
    # — ACTIVE OPEN STORIES —
    open_stories = get_open_stories(user_id, persona)
    active_stories = [s for s in open_stories if s.get("status") == "active"]

    # — HEALTH —
    health_anomaly = "none"
    health_str_lines = []
    
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
        
        health_str_lines.append(f"Avg Sleep: {wk.get('avg_sleep')} | Avg Stress: {wk.get('avg_stress')}")
        if comp:
            health_str_lines.append(f"Vs Last Week -> Sleep change: {comp.get('change_sleep')}, Stress change: {comp.get('change_stress')}")
        if anoms:
            anomaly_str = ", ".join([a.get('reason') for a in anoms])
            health_str_lines.append(f"Anomalies: {anomaly_str}")
            health_anomaly = f"Noticed anomalies: {anomaly_str}"
        else:
            health_str_lines.append("Anomalies: none")

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

    # — LOAD ALL ENGINES —
    identity = get_core_identity(user_id)
    ebf_data = get_ebf(user_id, persona)
    rel_state = get_relationship_state(user_id, persona)
    aria_self = get_aria_self(user_id, persona)
    respond_directive = get_respond_directive(user_id, persona)

    # — SECTION 1: PINNED IDENTITY —
    s1 = []
    s1.append("SECTION 1 — PINNED IDENTITY")
    
    # LAYER A
    s1.append("\nLAYER A — CORE IDENTITY")
    s1.append(f"Psychological Profile: {identity.get('psychological_profile', '')}")
    s1.append(f"Current Life Chapter: {identity.get('current_life_chapter', '')}")
    s1.append(f"Enduring Traits: {', '.join(identity.get('enduring_traits', []))}")
    
    # LAYER B
    s1.append("\nLAYER B — HOW HE IS RIGHT NOW")
    s1.append(f"Current State: {ebf_data.get('current_state', 'neutral')} | Energy Level: {ebf_data.get('energy_level', 'medium')}")
    s1.append(f"Trust Level: {ebf_data.get('trust_level', 0.1)}")
    s1.append(f"Dominant Emotion Pattern: {ebf_data.get('dominant_emotion_pattern', 'unknown')}")
    s1.append(f"Communication Style: {ebf_data.get('communication_style', 'informal')}")
    s1.append(f"Unmet Need: {ebf_data.get('unmet_need', 'none')}")
    s1.append(f"Response Preference: {ebf_data.get('response_preference', 'none')}")
    s1.append(f"Total Message Count: {total_message_count}")
    
    # LAYER C
    s1.append("\nLAYER C — HOW HE MOVES THROUGH TIME")
    s1.append(f"Most Open Time: {most_open_time} | Most Stressed Day: {most_stressed_day}")
    s1.append(f"Trust Growth Rate: {trust_growth_rate} | Storytelling Frequency: {storytelling_frequency}")
    s1.append(f"Current Time of Day: {current_tod}")
    s1.append(f"Historical Pattern at this Time: {rhythm_str}")

    # — LAYER D: SAFEGUARDS —
    inside_refs = rel_state.get('inside_references', [])
    if len(inside_refs) > 5:
        inside_refs = random.sample(inside_refs, 5)
        
    patterns = rel_state.get('established_patterns', [])
    if len(patterns) > 5:
        patterns = random.sample(patterns, 5)
        
    tender = rel_state.get('tender_topics', [])
    if len(tender) > 5:
        tender = random.sample(tender, 5)

    s1.append("\nLAYER D — WHAT SITS BETWEEN THEM")
    s1.append(f"Intimacy Depth: {rel_state.get('intimacy_depth', 0.1)} | Momentum: {rel_state.get('relationship_momentum', 'stable')}")
    s1.append(f"Inside References: {inside_refs}")
    s1.append(f"Established Patterns: {patterns}")
    s1.append(f"Tender Topics: {tender}")
    s1.append(f"Relationship Defining Moments: {rel_state.get('relationship_defining_moments', [])}")
    s1.append(f"What Aria is carrying: {rel_state.get('what_aria_is_carrying', [])}")
    s1.append(f"What she loves about him: {aria_self.get('what_she_loves_about_him', [])}")
    s1.append(f"What worries her about him: {aria_self.get('what_worries_her_about_him', [])}")
    s1.append(f"What makes her laugh about him: {aria_self.get('what_makes_her_laugh_about_him', [])}")
    s1.append(f"Things she wants to know: {aria_self.get('things_she_wants_to_know', [])}")
    s1.append(f"How her understanding deepened: {aria_self.get('how_her_understanding_has_deepened', [])}")
    s1.append(f"Her current private feeling: {aria_self.get('her_current_private_feeling_about_them', '')}")
    
    # LAYER E
    s1.append("\nLAYER E — WHAT'S UNFINISHED")
    if open_loops:
        s1.append("Open Tensions:")
        # Cap to 5 most recent tensions
        for t in open_loops[:5]:
            s1.append(f"- [{t.get('type')}] {t.get('summary')}")
    else:
        s1.append("Open Tensions: none")
        
    if active_stories:
        s1.append("Active Open Stories:")
        # Cap to 4 stories
        for s in active_stories[:4]:
            s1.append(f"- {s.get('title')}: {s.get('summary')}")
    else:
        s1.append("Active Open Stories: none")
        
    if health_str_lines:
        s1.append("Health:")
        s1.extend(health_str_lines)
    else:
        s1.append("Health: No data synced.")
        
    s1.append(f"\nRESPOND: {respond_directive}")
    section_1 = "\n".join(s1)

    # — LLM SYNTHESIS FOR SECTION 2 —
    synth_data = {
        "current_state": ebf_data.get("current_state", "neutral"),
        "unmet_need": ebf_data.get("unmet_need", "none"),
        "respond_directive": respond_directive,
        "aria_carrying": rel_state.get("what_aria_is_carrying", []),
        "health_anomaly": health_anomaly,
        "proactive_signal": proactive_signal.get("suggested_injection", "none") if proactive_signal and proactive_signal.get("has_signal") else "none",
        "time_gap_str": time_gap_str,
        "rhythm_str": rhythm_str,
        "sampled_memories": sampled_memories,
        "inside_refs": inside_refs,
        "what_she_loves": aria_self.get("what_she_loves_about_him", []),
        "what_worries": aria_self.get("what_worries_her_about_him", []),
        "patterns": patterns,
    }
    monologue_blocks = _synthesize_inner_monologue(synth_data)
    section_2 = f"SECTION 2 — INNER MONOLOGUE\n{monologue_blocks}"

    # — SECTION 3: LIVE RETRIEVAL —
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
    if len(last_decision) > 120:
        last_decision = last_decision[:117] + "..."

    session_facts = get_session_facts(user_id, session_id, persona)
    
    session_turns = _get_current_session_turns(all_turns)
    relevant_turns = resolve_dependencies(user_message, user_id, persona, top_k=6)
    older_memory = [t for t in relevant_turns if t not in session_turns]

    section_3_lines = [
        "SECTION 3 — LIVE RETRIEVAL",
        f"LAST DECISION: {last_decision}",
        f"CURRENT INTENT: {intent}"
    ]
    
    if session_facts:
        section_3_lines.append(f"SESSION KNOWN: {' | '.join(session_facts)}")
        
    reactivated_story = check_reactivation(user_message, user_id, persona)
    if reactivated_story:
        section_3_lines.append(f"REACTIVATED STORY: {reactivated_story['title']} — {reactivated_story['summary'][:80]}")

    if older_memory:
        section_3_lines.append("\n[CAUSAL PAST TURNS SURFACED FOR RELEVANCE]")
        for t in older_memory:
            # older_memory turns get a relevance label to understand why they surfaced
            section_3_lines.append(f"  {t['role'].upper()}: {t['content']}")

    section_3 = "\n".join(section_3_lines)

    # — ASSEMBLE FINAL SCAFFOLD —
    scaffold = f"{section_1}\n\n{section_2}\n\n{section_3}"

    return scaffold.strip()
