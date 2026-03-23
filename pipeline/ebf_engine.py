"""
Layer 3 — Emotional Behavioural Fingerprint (EBF)
Builds a profile of the user's emotional and communication patterns turn-by-turn.
No LLM involved — pure signal detection from message characteristics.
The EBF shapes the RESPOND tone instruction in the scaffold.
"""

import json
import os
import re
from datetime import datetime

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ebf.json")

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
    "last_updated": "",
}

# ── Persistence ───────────────────────────────────────────────────────────────

def _load() -> dict:
    if not os.path.exists(DATA_PATH):
        return dict(_DEFAULT_EBF)
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            # Merge with defaults in case new keys were added
            return {**_DEFAULT_EBF, **data}
        except json.JSONDecodeError:
            return dict(_DEFAULT_EBF)


def _save(ebf: dict):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    ebf["last_updated"] = datetime.utcnow().isoformat()
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(ebf, f, indent=2, ensure_ascii=False)


# ── Signal Detection ──────────────────────────────────────────────────────────

def _detect_arousal(text: str) -> str:
    """Detect energy/arousal level from punctuation and caps."""
    exclamations = text.count("!")
    caps_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)
    ellipsis = text.count("...")
    question_marks = text.count("?")

    if exclamations >= 2 or caps_ratio > 0.3:
        return "high"
    if ellipsis >= 2 or (question_marks >= 2):
        return "anxious"
    if exclamations == 0 and len(text) < 20:
        return "low"
    return "medium"


def _detect_style(text: str) -> str:
    """Detect communication style: formal, informal, direct."""
    lower = text.lower()
    informal_markers = ["u ", "ur ", "lol", "omg", "gonna", "wanna", "kinda",
                        "sorta", "idk", "tbh", "ngl", "im ", "cant ", "dont ", "its "]
    formal_markers = ["therefore", "however", "consequently", "furthermore",
                      "regarding", "with respect to", "in terms of"]

    informal_score = sum(1 for m in informal_markers if m in lower)
    formal_score = sum(1 for m in formal_markers if m in lower)

    if informal_score >= 2:
        return "informal"
    if formal_score >= 1:
        return "formal"
    return "direct"


def _detect_emotion_state(text: str) -> str:
    """Rough current emotional state from keywords."""
    lower = text.lower()
    states = {
        "excited": ["excited", "amazing", "can't wait", "love it", "awesome", "hyped"],
        "frustrated": ["frustrated", "annoying", "hate", "ugh", "fed up", "so tired of"],
        "anxious": ["worried", "scared", "anxious", "nervous", "not sure", "what if"],
        "sad": ["sad", "lonely", "miss", "hurt", "upset", "down", "low"],
        "reflective": ["thinking", "wondering", "realised", "realized", "felt like", "looking back"],
        "content": ["good", "fine", "okay", "alright", "happy", "stable"],
    }
    for state, keywords in states.items():
        if any(kw in lower for kw in keywords):
            return state
    return "neutral"


def _detect_unmet_need(text: str, current_state: str) -> str:
    """Guess unmet need from context."""
    lower = text.lower()
    if "nobody" in lower or "no one" in lower or "alone" in lower:
        return "wants to feel heard"
    if "don't know what to do" in lower or "help" in lower:
        return "needs guidance"
    if "i'm right" in lower or "agree with me" in lower or "what do you think" in lower:
        return "wants validation"
    if current_state == "excited":
        return "wants to share and be celebrated"
    if current_state == "frustrated":
        return "wants acknowledgment of frustration"
    return ""


def _infer_response_preference(style: str, arousal: str, msg_len: int) -> str:
    """Infer preferred response style for the scaffold RESPOND directive."""
    if style == "informal" and arousal == "high":
        return "punchy, match their high energy, stay grounded"
    if arousal == "anxious":
        return "calm, deeply grounding, clear and rational"
    if arousal == "low" or msg_len < 30:
        return "brief, clever, warm but not overbearing"
    if style == "formal":
        return "thoughtful, respect intelligence, subtle humour"
    # Default fallback that still preserves Aria's vibe
    return "balanced, grounded, cleverly framed, concise"


def _update_trust(ebf: dict, text: str) -> float:
    """Trust grows slowly as user shares more personal things."""
    lower = text.lower()
    personal_signals = [
        "i feel", "i felt", "i'm scared", "i'm worried", "to be honest",
        "tbh", "ngl", "i've never told", "don't tell anyone", "confession",
        "my family", "my friend", "my sister", "my brother", "i love",
    ]
    boost = sum(0.02 for s in personal_signals if s in lower)
    new_trust = min(1.0, ebf["trust_level"] + boost + 0.005)  # slow baseline growth
    return round(new_trust, 3)


# ── Public API ────────────────────────────────────────────────────────────────

def update_ebf(user_message: str) -> dict:
    """
    Update EBF based on the incoming user message.
    Returns the updated EBF dict.
    """
    ebf = _load()

    arousal = _detect_arousal(user_message)
    style = _detect_style(user_message)
    state = _detect_emotion_state(user_message)
    unmet_need = _detect_unmet_need(user_message, state)
    response_pref = _infer_response_preference(style, arousal, len(user_message))
    trust = _update_trust(ebf, user_message)

    ebf["energy_level"] = arousal
    ebf["communication_style"] = style
    ebf["current_state"] = state
    ebf["trust_level"] = trust
    ebf["response_preference"] = response_pref
    ebf["session_message_count"] = ebf.get("session_message_count", 0) + 1
    ebf["total_message_count"] = ebf.get("total_message_count", 0) + 1

    if unmet_need:
        ebf["unmet_need"] = unmet_need

    # Update dominant emotion pattern after enough data
    if ebf["total_message_count"] >= 5:
        ebf["dominant_emotion_pattern"] = (
            f"tends to be {state} with {style} communication at {arousal} energy"
        )

    _save(ebf)
    return ebf


def get_ebf() -> dict:
    return _load()


def get_ebf_summary() -> str:
    """Compact EBF line for the scaffold (5 tokens budget)."""
    ebf = _load()
    state = ebf.get("current_state", "neutral")
    style = ebf.get("communication_style", "neutral")
    energy = ebf.get("energy_level", "medium")
    return f"{state}, {style}, energy={energy}"


def get_respond_directive() -> str:
    """RESPOND line for scaffold (10 token budget)."""
    ebf = _load()
    pref = ebf.get("response_preference", "balanced, warm, concise")
    trust = ebf.get("trust_level", 0.1)
    # Add trust-level modulation
    if trust > 0.6:
        return f"{pref}; trust is high, can be more personal"
    return pref
