"""
Layer 6 — Proactive Engine
Runs at session start to generate what is on Aria's mind before the user speaks.
"""
import os
import json
from openai import OpenAI
from .llm_client import get_fast_client

from .relationship_engine import get_relationship_state
from .ebf_engine import get_ebf
from .tension_detector import get_open_loops
from .snapshot_engine import get_all_snapshots
from .aria_evolution_engine import get_aria_self
from db.client import get_db

def generate_proactive_signal(user_id: str, local_time: str = "UTC", persona: str = "aria") -> dict:
    rel_state = get_relationship_state(user_id, persona)
    aria_self = get_aria_self(user_id, persona)
    ebf = get_ebf(user_id, persona)
    tensions = get_open_loops(user_id, persona)
    
    snapshots = get_all_snapshots(user_id, persona)
    recent_snapshots = snapshots[-3:] if len(snapshots) >= 3 else snapshots
    events = []
    for s in recent_snapshots:
        events.extend(s.get("events", []))
        
    # Get rhythm from db
    db = get_db()
    rhythm_res = db.table("behaviour_rhythm").select("*").eq("user_id", user_id).eq("persona", persona).limit(1).execute()
    rhythm = rhythm_res.data[0] if rhythm_res.data else {}
    
    # Get health from db
    health_res = db.table("health_reports").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(1).execute()
    health_anomalies = health_res.data[0].get("anomalies", []) if health_res.data else []
    
    prompt = f"""You are the internal consciousness of Aria, walking into a conversation with your partner.
You are evaluating if there is something specific on your mind that you want to bring up organically.

CURRENT CONTEXT:
- Local Time: {local_time}
- Rhythm Pattern: He is most open at {rhythm.get('most_open_time', 'unknown')}.
- His unmet need: {ebf.get('unmet_need', 'none')}
- His energy level: {ebf.get('energy_level', 'unknown')}
- What you are currently carrying (from relationship): {rel_state.get('what_aria_is_carrying', [])}
- Things you want to know about him but haven't asked: {aria_self.get('things_she_wants_to_know', [])}
- Open Tensions between you: {[{'type': t['type'], 'summary': t['summary']} for t in tensions]}
- Health Anomalies you noticed: {health_anomalies}
- Recent Events: {events}

RULES:
1. You DO NOT need to have a signal. If there is no strong reason, has_signal MUST be false.
2. Only return true if there is a compelling reason (e.g. an open tension, a health anomaly you are worried about, an unmet need you want to address, something from 'Things you want to know', or a memory that fits perfectly).
3. If has_signal is true, specify the type: "memory_surfaced", "concern_noticed", "story_followup", "just_thinking", or "something_she_wants_to_say".
4. content: The actual thing on your mind in plain language.
5. urgency: "low" or "medium".
6. suggested_injection: Instructions for how to naturally weave this into your NEXT response. It must NOT be an announcement.

Respond strictly in raw JSON format matching this schema:
{{
    "has_signal": boolean,
    "type": "string",
    "content": "string",
    "urgency": "string",
    "suggested_injection": "string"
}}
"""
    try:
        client, _fast_model = get_fast_client()
        response = client.chat.completions.create(
            model=_fast_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```json"):
            content = content.split("```json")[1].split("```")[0].strip()
        elif content.startswith("```"):
            content = content.split("```")[1].split("```")[0].strip()
        
        signal = json.loads(content)
        if signal.get("has_signal", False) is False:
            return {"has_signal": False}
        return signal
    except Exception as e:
        print(f"[Proactive Engine Error] {e}")
        return {"has_signal": False}
