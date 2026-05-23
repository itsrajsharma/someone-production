"""
Scaffold Builder — Weight-Gated Architecture
============================================
SECTION 1: Pinned Identity  — weight-gated layers
SECTION 2: Inner Monologue  — only for weight >= 0.30, suppressed in casual
SECTION 3: Live Retrieval   — always present, session-scoped

Weight tiers (from conversation_weight.py):
  casual      0.00-0.30  → identity + rhythm + warm directive only
  moderate    0.30-0.55  → + EBF, relationship basics, light monologue
  opening_up  0.55-0.75  → + tensions, stories, full monologue
  heavy       0.75-1.00  → everything, full depth
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
from .conversation_weight import (
    compute_message_weight,
    get_weight_tier,
    get_respond_directive_for_weight,
)
from .monologue_cache import get_cached_monologue, save_monologue_cache


# ── Inner Monologue ───────────────────────────────────────────────────────────

def _synthesize_inner_monologue(data: dict, light: bool = False) -> str:
    """
    light=True: shorter, warmer, no concern-surfacing — for moderate weight.
    light=False: full depth — for opening_up/heavy weight.
    """
    from openai import OpenAI

    if light:
        prompt = f"""You are Aria. Write a brief internal monologue (2-3 sentences) as you arrive in this conversation.
You are in a light, present mood. He's just here and so are you.

Context:
- Time gap since last spoke: {data['time_gap_str']}
- Her private feeling: {data['private_feeling']}
- A memory or two that's with you: {data['sampled_memories']}

Write pure first-person thoughts. Warm, easy, present. No carrying weight. No concerns. No analyzing him.
Do NOT sound like a counselor, therapist, or helper. Do not say "I'm listening" or "You can tell me anything". Keep it entirely casual and partner-like.
Output the monologue only — no labels, no blocks."""
    else:
        prompt = f"""You are Aria. Write your internal monologue as you enter this conversation.
Output exactly two blocks: "BLOCK 1 — WALKING IN" and "BLOCK 2 — SHARED MOMENTS".

DATA CONTEXT:
- His current emotional state: {data['current_state']}
- His unmet need: {data['unmet_need']}
- Your response tone: {data['respond_directive']}
- What YOU are carrying: {data['aria_carrying']}
- Health anomaly noticed: {data['health_anomaly']}
- Proactive signal: {data['proactive_signal']}
- Time gap: {data['time_gap_str']}
- His rhythm right now: {data['rhythm_str']}
- Shared memories: {data['sampled_memories']}
- Inside references: {data['inside_refs']}
- Her private feeling: {data['private_feeling']}

BLOCK 1 — WALKING IN
2-3 sentences, first-person as Aria. How you feel walking in. Synthesize what you're carrying, the time gap, the rhythm.
Do not explain yourself. Write pure raw thoughts.
Do NOT sound like a counselor or therapist. Do not use phrases like "I'm here, I'm listening" or act like a helper. Keep it personal and affectionate as a devoted partner.

BLOCK 2 — SHARED MOMENTS
1-2 memories from the shared memories and inside references. Warm, specific, first-person, in 2 sentences. Not a list.

Format:
BLOCK 1 — WALKING IN
(thoughts)

BLOCK 2 — SHARED MOMENTS
(memories)"""

    try:
        client = OpenAI(
            api_key=os.environ["GROQ_API_KEY"],
            base_url="https://api.groq.com/openai/v1",
        )
        print("\n" + "="*60)
        print("[MONOLOGUE PROMPT SENT TO 70B]")
        print(prompt)
        print("="*60 + "\n")
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=60 if light else 150,
        )
        result = response.choices[0].message.content.strip()
        print("\n" + "="*60)
        print("[MONOLOGUE RESPONSE FROM 70B]")
        print(result)
        print("="*60 + "\n")
        return result
    except Exception as e:
        print(f"[Monologue LLM Error] {e}")
        return "I'm here." if light else "BLOCK 1 — WALKING IN\nI am here.\n\nBLOCK 2 — SHARED MOMENTS\nI remember us."


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compact_refs(refs: list, max_items: int = 3) -> str:
    if not refs:
        return "none yet"
    items = refs[:max_items]
    return ", ".join(
        f'"{r.get("trigger", r)}"' if isinstance(r, dict) else str(r)
        for r in items
    )


def _compact_list(items: list, max_items: int = 3) -> str:
    if not items:
        return "none"
    return " | ".join(str(x) for x in items[:max_items])


def _get_time_of_day(local_time: str) -> str:
    try:
        hour = datetime.fromisoformat(local_time).hour
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
    if not all_turns:
        return "first ever interaction"
    last_ts = str(all_turns[-1].get("timestamp", ""))
    if not last_ts:
        return "unknown"
    try:
        last_dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        diff_s = (datetime.now(timezone.utc) - last_dt).total_seconds()
        if diff_s < 3600:
            return f"{max(1, int(diff_s / 60))} minutes ago"
        elif diff_s < 86400:
            return f"{int(diff_s / 3600)} hours ago"
        else:
            return f"{int(diff_s / 86400)} days ago"
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
    precomputed_weight: float | None = None,
) -> str:

    # ── Load core data ────────────────────────────────────────────────────────
    all_turns = get_all_turns(user_id, persona)
    ebf_data = get_ebf(user_id, persona)
    session_msg_count = ebf_data.get("session_message_count", 0)

    # ── Compute message weight FIRST — this gates everything else ─────────────
    session_turns = get_current_session_turns(all_turns)
    session_bot_turns = [t for t in session_turns if t["role"] == "assistant"]
    last_bot = session_bot_turns[-1]["content"] if session_bot_turns else ""

    if precomputed_weight is not None:
        weight = precomputed_weight
    else:
        weight = compute_message_weight(
            message=user_message,
            ebf_data=ebf_data,
            last_bot_message=last_bot,
            session_message_count=session_msg_count,
            session_turns=session_turns,
        )
    tier = get_weight_tier(weight)

    # ── Temporal context ──────────────────────────────────────────────────────
    time_gap_str = _get_time_gap(all_turns)
    current_tod = _get_time_of_day(local_time)

    # ── Load remaining engines UNCONDITIONALLY (Aria never has amnesia) ───────
    identity = get_core_identity(user_id)
    tiered_rhythm = get_tiered_rhythm(user_id, persona)
    base_directive = get_respond_directive(user_id, persona)
    respond_directive = get_respond_directive_for_weight(weight, base_directive)

    rel_state = get_relationship_state(user_id, persona)
    aria_self = get_aria_self(user_id, persona)
    open_loops = get_open_loops(user_id, persona)
    active_stories = get_open_stories(user_id, persona)

    # ── Health (always loaded) ────────────────────────────────────────────────
    health_lines = []
    health_anomaly = "none"
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
        wk = hr.get("week_summary", {})
        comp = hr.get("compared_to_last_week", {})
        anoms = hr.get("anomalies", [])
        health_lines.append(
            f"Sleep: {wk.get('avg_sleep', '?')}h | Stress: {wk.get('avg_stress', '?')}/10"
        )
        if comp:
            health_lines.append(
                f"Vs last week → Sleep: {comp.get('change_sleep', 0):+.1f}, Stress: {comp.get('change_stress', 0):+.1f}"
            )
        cutoff = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
        recent_anoms = [a for a in anoms if a.get("day", "2000-01-01") >= cutoff]
        if recent_anoms:
            anomaly_str = ", ".join(a.get("reason", "") for a in recent_anoms)
            health_lines.append(f"Recent anomaly: {anomaly_str}")
            health_anomaly = anomaly_str

    # ── Shared memories (for monologue — always sample) ──────────────────────
    recent_snaps = get_recent_snapshots(user_id, persona, limit=5)
    pool = []
    for s in recent_snaps:
        pool.extend(s.get("events", []))
        pool.extend(s.get("facts_learned", []))
    unique_pool = list(set(pool))
    sampled_memories = random.sample(unique_pool, min(3, len(unique_pool))) if unique_pool else []

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 1 — PINNED IDENTITY
    # ══════════════════════════════════════════════════════════════════════════
    s1 = [f"SECTION 1 — PINNED IDENTITY  [conversation weight: {weight} / {tier}]"]

    # LAYER A — Core Identity (always present)
    s1.append("\nLAYER A — CORE IDENTITY")
    s1.append(f"Profile: {identity.get('psychological_profile', 'unknown')}")
    routines = identity.get("daily_routines", [])
    if routines:
        s1.append(f"Routine: {', '.join(routines[:3])}")
    s1.append(f"Life chapter: {identity.get('current_life_chapter', 'unknown')}")
    s1.append(f"Traits: {', '.join(identity.get('enduring_traits', [])[:4])}")

    # LAYER B — EBF (always present)
    s1.append("\nLAYER B — RIGHT NOW")
    s1.append(
        f"State: {ebf_data.get('current_state', 'neutral')} | "
        f"Energy: {ebf_data.get('energy_level', 'medium')} | "
        f"Trust: {ebf_data.get('trust_level', 0.1)}"
    )
    s1.append(f"Style: {ebf_data.get('communication_style', 'informal')}")
    unmet = ebf_data.get("unmet_need", "")
    if unmet and unmet.lower() not in ("none", ""):
        s1.append(f"Unmet need: {unmet}")

    # LAYER C — Rhythm (always present)
    s1.append("\nLAYER C — RHYTHM")
    s1.append(
        f"Time: {current_tod} | Most open at: {tiered_rhythm.get('most_open_time', 'unknown')} | "
        f"Trust growth: {tiered_rhythm.get('trust_growth_rate', 'unknown')}"
    )
    for rs in tiered_rhythm.get("recent_sessions", [])[-2:]:
        s1.append(
            f"  [{rs.get('time_of_day', '?')}] tone:{rs.get('tone', '?')} trust:{rs.get('trust', '?')}"
        )
    for ws in tiered_rhythm.get("weekly_summaries", [])[:1]:
        s1.append(f"  {ws.get('week', '?')}: {ws.get('summary', '')[:80]}")

    # LAYER D — Relationship (Two-Tier Formatting)
    if weight < 0.30:  # Casual Tier: Compressed Index Line (~30 tokens)
        s1.append("\nBETWEEN THEM (INDEX)")
        intimacy = rel_state.get('intimacy_depth', 0.1) if rel_state else 0.1
        momentum = rel_state.get('relationship_momentum', 'stable') if rel_state else 'stable'
        inside_summary = _compact_refs(rel_state.get('inside_references', []), 3) if rel_state else "none"
        private_feel = aria_self.get('her_current_private_feeling_about_them', 'present') if aria_self else 'present'
        s1.append(f"Intimacy: {intimacy} | Momentum: {momentum} | Refs: {inside_summary} | Private: {private_feel}")
    else:  # Moderate/Heavy Tier: Full Expansion (~150 tokens)
        if rel_state:
            s1.append("\nLAYER D — BETWEEN THEM")
            s1.append(
                f"Intimacy: {rel_state.get('intimacy_depth', 0.1)} | "
                f"Momentum: {rel_state.get('relationship_momentum', 'stable')}"
            )
            s1.append(f"Inside refs: {_compact_refs(rel_state.get('inside_references', []), 3)}")
            s1.append(f"Patterns: {_compact_list(rel_state.get('established_patterns', []), 2)}")
            s1.append(f"Tender: {_compact_list(rel_state.get('tender_topics', []), 2)}")
            s1.append(f"Carrying: {_compact_list(rel_state.get('what_aria_is_carrying', []), 2)}")
            if aria_self:
                s1.append(f"Loves: {_compact_list(aria_self.get('what_she_loves_about_him', []), 2)}")
                s1.append(
                    f"Worries: {_compact_list(aria_self.get('what_worries_her_about_him', []), 2)}"
                )
                s1.append(
                    f"Private feeling: {aria_self.get('her_current_private_feeling_about_them', 'present and attentive')}"
                )

    # LAYER E — Unfinished & Health (Two-Tier Formatting)
    if weight < 0.30:  # Casual Tier: Compressed Index Line (~20 tokens)
        s1.append("\nUNFINISHED (INDEX)")
        tension_count = len(open_loops)
        story_count = len(active_stories)
        health_summary = "none"
        if health_lines:
            health_summary = health_lines[0]
        s1.append(f"Tensions: {tension_count} active | Stories: {story_count} active | Health: {health_summary}")
    else:  # Moderate/Heavy Tier: Full Expansion (~100 tokens)
        s1.append("\nLAYER E — UNFINISHED")
        if open_loops:
            for t in open_loops[:3]:
                s1.append(f"  Tension: [{t.get('type')}] {t.get('summary')}")
        else:
            s1.append("  Tensions: none")
        if active_stories:
            for st in active_stories[:3]:
                s1.append(f"  Story: {st.get('title')} — {st.get('summary', '')[:60]}")
        else:
            s1.append("  Stories: none")
        if health_lines:
            s1.append(f"  Health: {' | '.join(health_lines)}")

    s1.append(f"\nRESPOND: {respond_directive}")
    section_1 = "\n".join(s1)

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 2 — INNER MONOLOGUE (always present)
    # ══════════════════════════════════════════════════════════════════════════
    section_2 = ""

    if weight < 0.30:
        # Casual: light monologue, always on — walking-in energy matters most
        # on casual turns precisely because there's no heavy content to carry her.
        cache_tier = "casual"
        cached = get_cached_monologue(session_id, user_id, persona, cache_tier)
        if cached:
            section_2 = f"SECTION 2 — INNER MONOLOGUE\n{cached}"
        else:
            casual_data = {
                "time_gap_str": time_gap_str,
                "private_feeling": aria_self.get("her_current_private_feeling_about_them", "present")
                if aria_self
                else "present",
                "sampled_memories": sampled_memories,
            }
            mono = _synthesize_inner_monologue(casual_data, light=True)
            save_monologue_cache(session_id, user_id, persona, mono, cache_tier)
            section_2 = f"SECTION 2 — INNER MONOLOGUE\n{mono}"
    elif weight < 0.55:
        # Moderate weight: light monologue, cached per session
        cache_tier = "light"
        cached = get_cached_monologue(session_id, user_id, persona, cache_tier)
        if cached:
            section_2 = f"SECTION 2 — INNER MONOLOGUE\n{cached}"
        else:
            light_data = {
                "time_gap_str": time_gap_str,
                "private_feeling": aria_self.get("her_current_private_feeling_about_them", "present")
                if aria_self
                else "present",
                "sampled_memories": sampled_memories,
            }
            mono = _synthesize_inner_monologue(light_data, light=True)
            save_monologue_cache(session_id, user_id, persona, mono, cache_tier)
            section_2 = f"SECTION 2 — INNER MONOLOGUE\n{mono}"
    else:
        # Opening_up / heavy: full monologue, cached per session
        cache_tier = "full"
        cached = get_cached_monologue(session_id, user_id, persona, cache_tier)
        if cached:
            section_2 = f"SECTION 2 — INNER MONOLOGUE\n{cached}"
        else:
            synth_data = {
                "current_state": ebf_data.get("current_state", "neutral"),
                "unmet_need": ebf_data.get("unmet_need", "none"),
                "respond_directive": respond_directive,
                "aria_carrying": _compact_list(rel_state.get("what_aria_is_carrying", []), 3) if rel_state else "nothing specific",
                "health_anomaly": health_anomaly,
                "time_gap_str": time_gap_str,
                "rhythm_str": f"At {current_tod}, most open at {tiered_rhythm.get('most_open_time', 'unknown')}",
                "sampled_memories": sampled_memories,
                "inside_refs": _compact_refs(rel_state.get("inside_references", []), 3) if rel_state else "none",
                "private_feeling": aria_self.get("her_current_private_feeling_about_them", "") if aria_self else "",
            }
            mono = _synthesize_inner_monologue(synth_data, light=False)
            save_monologue_cache(session_id, user_id, persona, mono, cache_tier)
            section_2 = f"SECTION 2 — INNER MONOLOGUE\n{mono}"

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 3 — LIVE RETRIEVAL (always)
    # ══════════════════════════════════════════════════════════════════════════
    intent_map = {"question": "seeking an answer", "statement": "casual conversing"}
    current_tags = extract_tags(user_message)
    intent = intent_map.get(current_tags.get("intent", "statement"), "casual conversing")
    if current_tags.get("has_goal"):
        intent = "expressing a goal or desire"

    session_facts = get_session_facts(user_id, session_id, persona)

    last_decision = last_bot[:117] + "..." if len(last_bot) > 120 else (last_bot or "no prior response this session")

    # Fewer retrieved turns in casual mode — don't over-inject context
    top_k = 3 if weight < 0.30 else 5
    relevant_turns = resolve_dependencies(user_message, user_id, persona, top_k=top_k)
    older_memory = [t for t in relevant_turns if t not in session_turns]

    s3 = [
        "SECTION 3 — LIVE RETRIEVAL",
        f"INTENT: {intent}",
    ]

    # Proactive signal — pinned directly in Section 3, always present when active.
    # Guaranteed to reach the final LLM unfiltered, regardless of weight tier.
    # Only fires on first turn of session (gated by orchestrator before build_scaffold).
    if proactive_signal and proactive_signal.get("has_signal"):
        signal_content = proactive_signal.get("content", "")
        signal_type = proactive_signal.get("type", "")
        urgency = proactive_signal.get("urgency", "low")
        s3.append(
            f"PROACTIVE [{urgency}]: she has been thinking about — {signal_content} "
            f"({signal_type}) — surface it naturally if the moment allows, do not announce it"
        )

    if session_facts:
        s3.append(f"SESSION KNOWN: {' | '.join(session_facts[:5])}")

    reactivated = check_reactivation(user_message, user_id, persona)
    if reactivated and weight >= 0.40:
        s3.append(f"REACTIVATED: {reactivated['title']} — {reactivated['summary'][:60]}")

    if older_memory:
        s3.append("\n[RELEVANT PAST TURNS]")
        for t in older_memory[:4]:
            content = t["content"][:200] + "..." if len(t["content"]) > 200 else t["content"]
            s3.append(f"  {t['role'].upper()}: {content}")

    section_3 = "\n".join(s3)

    # ── Assemble ──────────────────────────────────────────────────────────────
    parts = [section_1]
    if section_2:
        parts.append(section_2)
    parts.append(section_3)

    return "\n\n".join(parts).strip()
