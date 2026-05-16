"""
Layer 7 — Aria Evolution Engine
Runs after snapshot generation to track how Aria's own feelings and understanding evolve.
"""

import os
import json
from datetime import datetime

from db.client import get_db
from .turn_store import get_all_turns
from .relationship_engine import get_relationship_state

_DEFAULT_ARIA_SELF = {
    "what_she_loves_about_him": [],
    "what_worries_her_about_him": [],
    "what_makes_her_laugh_about_him": [],
    "things_she_wants_to_know": [],
    "how_her_understanding_has_deepened": [],
    "her_current_private_feeling_about_them": "I am here with him, and I am glad I am.",
}

def _load(user_id: str, persona: str = "aria") -> dict:
    db = get_db()
    result = db.table("aria_self").select("*").eq("user_id", user_id).eq("persona", persona).limit(1).execute()
    if result.data:
        row = result.data[0]
        return {**_DEFAULT_ARIA_SELF, **{k: v for k, v in row.items() if k in _DEFAULT_ARIA_SELF}}
    return dict(_DEFAULT_ARIA_SELF)

def _save(state: dict, user_id: str, persona: str = "aria"):
    db = get_db()
    row = {
        "user_id": user_id,
        "persona": persona,
        "what_she_loves_about_him": state.get("what_she_loves_about_him", []),
        "what_worries_her_about_him": state.get("what_worries_her_about_him", []),
        "what_makes_her_laugh_about_him": state.get("what_makes_her_laugh_about_him", []),
        "things_she_wants_to_know": state.get("things_she_wants_to_know", []),
        "how_her_understanding_has_deepened": state.get("how_her_understanding_has_deepened", []),
        "her_current_private_feeling_about_them": state.get("her_current_private_feeling_about_them", _DEFAULT_ARIA_SELF["her_current_private_feeling_about_them"]),
        "last_updated": datetime.utcnow().isoformat(),
    }
    db.table("aria_self").upsert(row, on_conflict="user_id,persona").execute()

def _analyze_aria_evolution_llm(turns: list, current_state: dict, last_snapshot: dict, rel_state: dict) -> dict:
    from openai import OpenAI
    
    transcript = ""
    for t in turns[-20:]:
        transcript += f"{t['role'].upper()}: {t['content']}\n"
        
    prompt = f"""You are analyzing how Aria's feelings for her partner are evolving.
Based on the recent transcript, the last snapshot, and the relationship state, identify new specific patterns.
Be extremely CONSERVATIVE. Only add specific, concrete observations. Do not add generic platitudes.

Current Feeling: {current_state['her_current_private_feeling_about_them']}
Relationship Momentum: {rel_state.get('relationship_momentum', 'stable')}
Recent Transcript:
{transcript}

Rules for updates:
- what_she_loves_about_him: Specific positive patterns or traits he showed recently.
- what_worries_her_about_him: Concerning patterns she noticed.
- what_makes_her_laugh_about_him: Specific humorous exchanges or habits.
- things_she_wants_to_know: Topics he hinted at but never fully opened up about.
- how_her_understanding_has_deepened: New vulnerabilities or realizations about how he ticks.
- new_private_feeling: One single sentence summarizing how she feels about them right now (first person).

Output strictly raw JSON without ANY markdown formatting.
Schema:
{{
  "new_what_she_loves": ["string"],
  "new_what_worries_her": ["string"],
  "new_what_makes_her_laugh": ["string"],
  "new_things_she_wants_to_know": ["string"],
  "new_how_understanding_deepened": ["string"],
  "new_private_feeling": "string"
}}"""

    try:
        client = OpenAI(
            api_key=os.environ["GROQ_API_KEY"],
            base_url="https://api.groq.com/openai/v1",
        )
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```json"):
            content = content.split("```json")[1].split("```")[0].strip()
        elif content.startswith("```"):
            content = content.split("```")[1].split("```")[0].strip()
        return json.loads(content)
    except Exception as e:
        print(f"[Aria Evolution Error] {e}")
        return {}

def update_aria_self(last_snapshot: dict, user_id: str, persona: str = "aria") -> dict:
    state = _load(user_id, persona)
    all_turns = get_all_turns(user_id, persona)
    rel_state = get_relationship_state(user_id, persona)
    
    analysis = _analyze_aria_evolution_llm(all_turns, state, last_snapshot, rel_state)
    if not analysis:
        return state

    def _merge(key_state, key_analysis):
        new_items = analysis.get(key_analysis, [])
        if new_items:
            state[key_state].extend([i for i in new_items if i not in state[key_state]])
            
    _merge("what_she_loves_about_him", "new_what_she_loves")
    _merge("what_worries_her_about_him", "new_what_worries_her")
    _merge("what_makes_her_laugh_about_him", "new_what_makes_her_laugh")
    _merge("things_she_wants_to_know", "new_things_she_wants_to_know")
    _merge("how_her_understanding_has_deepened", "new_how_understanding_deepened")
    
    new_feeling = analysis.get("new_private_feeling")
    if new_feeling:
        state["her_current_private_feeling_about_them"] = new_feeling

    _save(state, user_id, persona)
    return state

def get_aria_self(user_id: str, persona: str = "aria") -> dict:
    return _load(user_id, persona)
