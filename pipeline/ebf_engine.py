"""
Layer 3 — Emotional Behavioural Fingerprint (EBF)
Builds a profile of the user's emotional and communication patterns turn-by-turn.
No file I/O — one row per user+persona in Supabase, upserted on every update.
"""

import os
from datetime import datetime

from db.client import get_db

# Default EBF state
_DEFAULT_EBF = {
    "dominant_emotion_pattern": "unknown",
    "communication_style": "neutral",
    "trust_level": 0.10,
    "current_state": "neutral",
    "unmet_need": "",
    "response_preference": "balanced",
    "session_message_count": 0,
    "total_message_count": 0,
    "energy_level": "medium",
    "current_session_id": "",
}


# ── Persistence ───────────────────────────────────────────────────────────────

def _load(user_id: str, persona: str = "aria") -> dict:
    db = get_db()
    result = (
        db.table("ebf")
        .select("*")
        .eq("user_id", user_id)
        .eq("persona", persona)
        .limit(1)
        .execute()
    )
    if result.data:
        row = result.data[0]
        # Merge with defaults in case new keys were added
        return {**_DEFAULT_EBF, **{k: v for k, v in row.items() if k in _DEFAULT_EBF or k == "last_updated"}}
    return dict(_DEFAULT_EBF)


def _save(ebf: dict, user_id: str, persona: str = "aria"):
    db = get_db()
    row = {
        "user_id": user_id,
        "persona": persona,
        "dominant_emotion_pattern": ebf.get("dominant_emotion_pattern", "unknown"),
        "communication_style": ebf.get("communication_style", "neutral"),
        "trust_level": ebf.get("trust_level", 0.10),
        "current_state": ebf.get("current_state", "neutral"),
        "unmet_need": ebf.get("unmet_need", ""),
        "response_preference": ebf.get("response_preference", "balanced"),
        "session_message_count": ebf.get("session_message_count", 0),
        "total_message_count": ebf.get("total_message_count", 0),
        "energy_level": ebf.get("energy_level", "medium"),
        "current_session_id": ebf.get("current_session_id", ""),
        "last_updated": datetime.utcnow().isoformat(),
    }
    db.table("ebf").upsert(row, on_conflict="user_id,persona").execute()


# ── Signal Detection ──────────────────────────────────────────────────────────

def _analyze_ebf_llm(user_message: str, current_ebf: dict) -> dict:
    from openai import OpenAI
from .llm_client import get_fast_client
    import json

    prompt = f"""Analyze the following user message to determine their current emotional and communicative state.
Output strictly raw JSON without ANY markdown formatting.
Schema:
{{
  "arousal": "low, medium, or high",
  "style": "formal, informal, or direct",
  "state": "neutral, excited, frustrated, anxious, sad, reflective, content, or casual",
  "unmet_need": "short phrase describing what they want (use 'none' if casually chatting or message is very short)",
  "response_preference": "describes HOW Aria sounds — tone only, adjectives only, never verbs or actions. Examples: 'quiet and warm', 'playful and light', 'present but brief', 'soft and close'"
}}

CRITICAL RULES:
- If the message is 5 words or fewer, a single-word response, or just a greeting — default state to 'neutral' or 'casual'. Do NOT infer frustration, anxiety, or sadness from short messages.
- Denials like 'no', 'no i am not', 'i am fine' are NOT signs of frustration — they are casual disagreements. State should be 'neutral'.
- Only classify as 'frustrated' if the message contains explicit frustration signals (cursing, strong complaints, "this is so annoying" etc).
- Current state context (for stability): {current_ebf.get('current_state', 'neutral')}. Only change state if the new message gives clear evidence. Do not flip from neutral to negative on ambiguous input.

User Message: "{user_message}"
"""
    try:
        client, _fast_model = get_fast_client()
        response = client.chat.completions.create(
            model=_fast_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```json"):
            content = content.split("```json")[1].split("```")[0].strip()
        elif content.startswith("```"):
            content = content.split("```")[1].split("```")[0].strip()
        result = json.loads(content)
        return {
            "arousal": result.get("arousal", "medium"),
            "style": result.get("style", "direct"),
            "state": result.get("state", "neutral"),
            "unmet_need": result.get("unmet_need", ""),
            "response_preference": result.get("response_preference", "balanced, grounded"),
        }
    except Exception as e:
        print(f"[EBF LLM Error] {e}")
        return {
            "arousal": "medium", "style": "direct",
            "state": "neutral", "unmet_need": "",
            "response_preference": "balanced, grounded, cleverly framed, concise",
        }


def _update_trust(ebf: dict, text: str) -> float:
    """Trust grows slowly as user shares more personal things."""
    lower = text.lower()
    personal_signals = [
        "i feel", "i felt", "i'm scared", "i'm worried", "to be honest",
        "tbh", "ngl", "i've never told", "don't tell anyone", "confession",
        "my family", "my friend", "my sister", "my brother", "i love",
    ]
    boost = sum(0.02 for s in personal_signals if s in lower)
    new_trust = min(1.0, ebf["trust_level"] + boost + 0.005)
    return round(new_trust, 3)


# ── Public API ────────────────────────────────────────────────────────────────

def update_ebf(user_message: str, user_id: str, session_id: str = "", persona: str = "aria") -> dict:
    """Update EBF based on the incoming user message. Returns the updated EBF dict."""
    ebf = _load(user_id, persona)

    llm_ebf = _analyze_ebf_llm(user_message, ebf)
    trust = _update_trust(ebf, user_message)

    # Reset session counter and volatile state if this is a new session
    stored_session = ebf.get("current_session_id", "")
    if session_id and session_id != stored_session:
        ebf["session_message_count"] = 0
        ebf["current_session_id"] = session_id
        # Clear volatile per-session state so stale emotions don't leak
        ebf["unmet_need"] = ""
        ebf["current_state"] = "neutral"

    ebf["energy_level"] = llm_ebf["arousal"]
    ebf["communication_style"] = llm_ebf["style"]
    ebf["current_state"] = llm_ebf["state"]
    ebf["trust_level"] = trust
    ebf["response_preference"] = llm_ebf["response_preference"]
    ebf["session_message_count"] = ebf.get("session_message_count", 0) + 1
    ebf["total_message_count"] = ebf.get("total_message_count", 0) + 1

    # Always take the LLM's current assessment — clear stale needs
    ebf["unmet_need"] = llm_ebf.get("unmet_need", "")

    if ebf["total_message_count"] >= 5:
        ebf["dominant_emotion_pattern"] = (
            f"tends to be {llm_ebf['state']} with {llm_ebf['style']} communication at {llm_ebf['arousal']} energy"
        )

    _save(ebf, user_id, persona)
    return ebf


def get_ebf(user_id: str, persona: str = "aria") -> dict:
    return _load(user_id, persona)


def get_ebf_summary(user_id: str, persona: str = "aria") -> str:
    """Compact EBF line for the scaffold."""
    ebf = _load(user_id, persona)
    state = ebf.get("current_state", "neutral")
    style = ebf.get("communication_style", "neutral")
    energy = ebf.get("energy_level", "medium")
    return f"{state}, {style}, energy={energy}"


def get_respond_directive(user_id: str, persona: str = "aria") -> str:
    """RESPOND line for scaffold."""
    ebf = _load(user_id, persona)
    pref = ebf.get("response_preference", "balanced, warm, concise")
    trust = ebf.get("trust_level", 0.1)
    if trust > 0.6:
        return f"{pref}; trust is high, can be more personal"
    return pref
