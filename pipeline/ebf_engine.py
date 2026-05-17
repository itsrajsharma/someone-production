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
        "last_updated": datetime.utcnow().isoformat(),
    }
    db.table("ebf").upsert(row, on_conflict="user_id,persona").execute()


# ── Signal Detection ──────────────────────────────────────────────────────────

def _analyze_ebf_llm(user_message: str, current_ebf: dict) -> dict:
    from openai import OpenAI
    import json

    prompt = f"""Analyze the following user message to determine their current emotional and communicative state.
Output strictly raw JSON without ANY markdown formatting.
Schema:
{{
  "arousal": "low, medium, high, or anxious",
  "style": "formal, informal, or direct",
  "state": "excited, frustrated, anxious, sad, reflective, content, or casual",
  "unmet_need": "short phrase describing what they want out of this interaction (use 'none' if they are just casually chatting)",
  "response_preference": "describes HOW Aria sounds, never WHAT she does. It is a tone, not an instruction. Never use verbs. Never suggest actions. Adjectives only. Valid examples: 'quiet and warm', 'playful and light', 'present but brief', 'soft and close', 'steady, no pressure'"
}}

User Message: "{user_message}"
"""
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

def update_ebf(user_message: str, user_id: str, persona: str = "aria") -> dict:
    """Update EBF based on the incoming user message. Returns the updated EBF dict."""
    ebf = _load(user_id, persona)

    llm_ebf = _analyze_ebf_llm(user_message, ebf)
    trust = _update_trust(ebf, user_message)

    ebf["energy_level"] = llm_ebf["arousal"]
    ebf["communication_style"] = llm_ebf["style"]
    ebf["current_state"] = llm_ebf["state"]
    ebf["trust_level"] = trust
    ebf["response_preference"] = llm_ebf["response_preference"]
    ebf["session_message_count"] = ebf.get("session_message_count", 0) + 1
    ebf["total_message_count"] = ebf.get("total_message_count", 0) + 1

    if llm_ebf["unmet_need"]:
        ebf["unmet_need"] = llm_ebf["unmet_need"]

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
