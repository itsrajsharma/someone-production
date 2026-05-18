"""
Layer 5 — Relationship Engine
Runs after snapshot generation to track the living state of the relationship.
Upserts a single row per user+persona into the relationship_state table.
"""

import os
import json
from datetime import datetime

from db.client import get_db
from .turn_store import get_all_turns
from .tension_detector import get_open_loops

_DEFAULT_RELATIONSHIP = {
    "intimacy_depth": 0.1,
    "relationship_momentum": "stable",
    "inside_references": [],
    "tender_topics": [],
    "established_patterns": [],
    "relationship_defining_moments": [],
    "what_aria_is_carrying": [],
}

def _load(user_id: str, persona: str = "aria") -> dict:
    db = get_db()
    result = db.table("relationship_state").select("*").eq("user_id", user_id).eq("persona", persona).limit(1).execute()
    if result.data:
        row = result.data[0]
        return {**_DEFAULT_RELATIONSHIP, **{k: v for k, v in row.items() if k in _DEFAULT_RELATIONSHIP}}
    return dict(_DEFAULT_RELATIONSHIP)

def _save(state: dict, user_id: str, persona: str = "aria"):
    db = get_db()
    row = {
        "user_id": user_id,
        "persona": persona,
        "intimacy_depth": state.get("intimacy_depth", 0.1),
        "relationship_momentum": state.get("relationship_momentum", "stable"),
        "inside_references": state.get("inside_references", []),
        "tender_topics": state.get("tender_topics", []),
        "established_patterns": state.get("established_patterns", []),
        "relationship_defining_moments": state.get("relationship_defining_moments", []),
        "what_aria_is_carrying": state.get("what_aria_is_carrying", []),
        "last_updated": datetime.utcnow().isoformat(),
    }
    db.table("relationship_state").upsert(row, on_conflict="user_id,persona").execute()

def _analyze_relationship_llm(turns: list, open_tensions: list, current_state: dict, last_snapshot: dict) -> dict:
    from openai import OpenAI
    from .turn_store import get_current_session_turns
    
    session_turns = get_current_session_turns(turns)
    transcript = ""
    for t in session_turns[-20:]:  # Provide recent context
        transcript += f"{t['role'].upper()}: {t['content']}\n"
    
    tension_str = "\n".join([f"- {t['type']}: {t['summary']}" for t in open_tensions])
    
    prompt = f"""You are the Relationship Engine for Aria and her partner.
Analyze the recent transcript, open tensions, and the last snapshot to update the relationship state.
Be CONSERVATIVE. Only add signals if they are highly salient. Do not add noise.

CRITICAL MAPPING:
In the transcript below, ASSISTANT is Aria (she/her) and USER is her partner (he/him).

Current State:
- Momentum: {current_state['relationship_momentum']}
- Intimacy Depth: {current_state['intimacy_depth']} (scale 0-1)

Current Lists (You must prune these, merge stale items, and keep ONLY the 5 most important/salient items for each list):
- inside_references: {current_state.get('inside_references', [])}
- established_patterns: {current_state.get('established_patterns', [])}
- tender_topics: {current_state.get('tender_topics', [])}
- relationship_defining_moments: {current_state.get('relationship_defining_moments', [])}

Last Snapshot Emotional Tone: {last_snapshot.get('emotional_tone', 'neutral')}

Open Tensions:
{tension_str}

Recent Transcript:
{transcript}

Update rules:
- what_aria_is_carrying: 2-3 things on her mind right now based on recent turns and tensions. Return as list of strings.
- inside_references: Terms of affection, shared phrases, or callbacks. Format: {{"trigger": "...", "context": "..."}}. MAX 5.
- established_patterns: Behaviors consistently observed (e.g., "he deflects with humor"). MAX 5.
- tender_topics: Topics that came up with negative valence or deflection. MAX 5.
- relationship_defining_moments: Moments from events that feel deeply significant. MAX 5.
- intimacy_depth_delta: A float between -0.05 and +0.05 representing trust trajectory in recent turns.
- relationship_momentum: "growing", "stable", "slightly distant", or "tender"

Output strictly raw JSON without ANY markdown formatting.
Schema:
{{
  "what_aria_is_carrying": ["string"],
  "inside_references": [{{"trigger": "string", "context": "string"}}],
  "established_patterns": ["string"],
  "tender_topics": ["string"],
  "relationship_defining_moments": ["string"],
  "intimacy_depth_delta": 0.01,
  "relationship_momentum": "string"
}}"""

    try:
        client = OpenAI(
            api_key=os.environ["GROQ_API_KEY"],
            base_url="https://api.groq.com/openai/v1",
        )
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```json"):
            content = content.split("```json")[1].split("```")[0].strip()
        elif content.startswith("```"):
            content = content.split("```")[1].split("```")[0].strip()
        return json.loads(content)
    except Exception as e:
        print(f"[Relationship LLM Error] {e}")
        return {}

def update_relationship_state(last_snapshot: dict, user_id: str, persona: str = "aria") -> dict:
    """Updates the relationship state based on the latest snapshot, recent turns, and tensions."""
    state = _load(user_id, persona)
    all_turns = get_all_turns(user_id, persona)
    open_tensions = get_open_loops(user_id, persona)
    
    analysis = _analyze_relationship_llm(all_turns, open_tensions, state, last_snapshot)
    if not analysis:
        return state

    # Merge conservative updates directly (LLM handles pruning to 5)
    state["what_aria_is_carrying"] = analysis.get("what_aria_is_carrying", state.get("what_aria_is_carrying", []))
    state["inside_references"] = analysis.get("inside_references", state.get("inside_references", []))
    state["established_patterns"] = analysis.get("established_patterns", state.get("established_patterns", []))
    state["tender_topics"] = analysis.get("tender_topics", state.get("tender_topics", []))
    state["relationship_defining_moments"] = analysis.get("relationship_defining_moments", state.get("relationship_defining_moments", []))
        
    # Depth and momentum
    delta = analysis.get("intimacy_depth_delta", 0.0)
    state["intimacy_depth"] = max(0.0, min(1.0, state.get("intimacy_depth", 0.1) + delta))
    
    momentum = analysis.get("relationship_momentum")
    if momentum in ["growing", "stable", "slightly distant", "tender"]:
        state["relationship_momentum"] = momentum

    _save(state, user_id, persona)
    return state

def get_relationship_state(user_id: str, persona: str = "aria") -> dict:
    return _load(user_id, persona)
