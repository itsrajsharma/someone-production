"""
Conversation Weight Layer
========================
Computes a single float (0.0 → 1.0) representing the emotional/contextual
weight of the current message. This is the gating signal for the scaffold.

0.0 = purely casual ("hi", "hey", "yes", "ok")
1.0 = fully open, heavy, distressed ("I'm scared", "had a fight", "I feel lost")

Pure Python — no LLM call, no DB call. Takes <1ms.
Called before build_scaffold() so the scaffold knows what to include.
"""

import re

# ── Keyword Signal Tables ─────────────────────────────────────────────────────

_GREETING_PATTERNS = re.compile(
    r"^\s*(hi|hey|hello|heyy|hiii|yo|sup|hola|hii|hiiii|what'?s up|wsg|heyyy)\b",
    re.IGNORECASE,
)

_DISCLOSURE_KEYWORDS = [
    "feel", "feeling", "felt", "honestly", "to be honest", "i think", "i believe",
    "scared", "afraid", "worried", "anxious", "nervous", "depressed", "hopeless",
    "excited", "happy", "proud", "grateful", "confused", "lost", "stuck",
    "my family", "my mom", "my dad", "my sister", "my brother", "my friend",
    "broke up", "fight", "argument", "crying", "cried", "hurt", "broken",
    "tired of", "done with", "can't anymore", "overwhelmed",
    "want to tell you", "need to tell you", "something happened",
]

_TOPIC_KEYWORDS = [
    "health", "sleep", "stress", "anxiety", "depression", "therapy",
    "work", "job", "deadline", "fired", "quit", "promotion",
    "money", "debt", "broke", "loan",
    "relationship", "girlfriend", "boyfriend", "crush", "dating",
    "death", "died", "funeral", "grief", "loss",
    "sick", "hospital", "doctor", "diagnosis",
    "exam", "failed", "failing", "college", "university",
]

_DEFLECTION_SIGNALS = [
    "nevermind", "forget it", "anyway", "doesn't matter", "nothing",
    "forget it", "it's fine", "i'm fine", "nvm",
]

_EXPLICIT_HEAVY = [
    "i'm scared", "i am scared", "i'm lost", "i feel lost", "i can't",
    "please", "help me", "don't know what to do", "falling apart",
    "breaking down", "don't know anymore",
]


# ── Core Computation ──────────────────────────────────────────────────────────

def classify_message_weight_llm(
    message: str,
    session_turns: list = None,
) -> str:
    """
    Uses llama-3.1-8b-instant to classify the emotional/contextual weight of a message.
    Returns: 'casual', 'moderate', or 'heavy'.
    """
    import os
    from openai import OpenAI
from .llm_client import get_fast_client

    # Format the last 3 turns as context
    context = ""
    if session_turns:
        for turn in session_turns[-3:]:
            role = "user" if turn["role"] == "user" else "assistant"
            content = turn["content"]
            if len(content) > 150:
                content = content[:147] + "..."
            context += f"{role.upper()}: {content}\n"
    if not context:
        context = "No prior session turns."

    prompt = f"""You are classifying a user message to determine if this conversation moment is casual or emotionally significant.

CLASSIFICATION RULES:
- casual: greetings, light banter, deflections, routine logistics ("hey", "nvm it's fine", "anyway what should we watch", "doing good", "ok cool", "what about you")
- moderate: mild vulnerability, sharing details of their day, routine emotional updates ("a bit tired today", "had a busy day", "just finished it", "I'm okay I guess")
- heavy: high vulnerability, distress, deep emotional topics, or severe anxiety ("I'm scared", "I feel lost", "had a huge fight", "breaking down")

CONTEXT (Last 3 turns):
{context}

USER MESSAGE: "{message}"

Identify the classification. Respond with exactly one word: casual, moderate, or heavy."""

    try:
        client, _fast_model = get_fast_client()
        response = client.chat.completions.create(
            model=_fast_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=10,
        )
        result = response.choices[0].message.content.strip().lower()
        for category in ["casual", "moderate", "heavy"]:
            if category in result:
                return category
        return "casual"
    except Exception as e:
        print(f"[Weight LLM Classification Error] {e}")
        return "fallback"


def compute_message_weight(
    message: str,
    ebf_data: dict,
    last_bot_message: str = "",
    session_message_count: int = 0,
    session_turns: list = None,
) -> float:
    """
    Returns a float 0.0–1.0 representing conversation weight.
    First attempts to classify using llama-3.1-8b-instant.
    Falls back to python heuristics if the LLM call fails.
    """
    # 1. Attempt LLM classification
    category = classify_message_weight_llm(message, session_turns)
    
    if category != "fallback":
        mapping = {
            "casual": 0.15,
            "moderate": 0.45,
            "heavy": 0.80
        }
        return mapping.get(category, 0.15)

    # 2. Fallback to Python heuristics if LLM fails
    msg = message.strip().lower()
    words = msg.split()
    word_count = len(words)
    weight = 0.0

    # Hard floor: very short messages are always light
    if word_count <= 2 and not any(kw in msg for kw in _DISCLOSURE_KEYWORDS + _TOPIC_KEYWORDS):
        return 0.05

    # Greeting pattern: floor at 0.08
    if _GREETING_PATTERNS.match(msg) and word_count <= 5:
        return 0.08

    # Explicit heavy signals: instant high weight
    if any(kw in msg for kw in _EXPLICIT_HEAVY):
        return 0.80

    # Deflection: moderate weight
    if any(kw in msg for kw in _DEFLECTION_SIGNALS):
        weight = max(weight, 0.45)

    # Signal 1: Message length
    length_score = min(word_count / 40.0, 0.25)
    weight += length_score

    # Signal 2: Personal disclosure keywords
    disclosure_hits = sum(1 for kw in _DISCLOSURE_KEYWORDS if kw in msg)
    weight += min(disclosure_hits * 0.15, 0.35)

    # Signal 3: Topic keywords
    topic_hits = sum(1 for kw in _TOPIC_KEYWORDS if kw in msg)
    weight += min(topic_hits * 0.12, 0.25)

    # Signal 4: EBF energy level
    energy = ebf_data.get("energy_level", "medium")
    energy_bonus = {"low": 0.15, "medium": 0.05, "high": 0.0}.get(energy, 0.05)
    if word_count > 4:
        weight += energy_bonus

    # Signal 5: EBF state
    state = ebf_data.get("current_state", "neutral")
    if weight > 0.2 and state in ("anxious", "sad", "distressed"):
        weight += 0.15
    elif weight > 0.3 and state == "frustrated":
        weight += 0.08

    # Signal 6: Question mark
    if "?" in message and word_count > 5:
        weight += 0.05

    # First message of session: slight dampening
    if session_message_count <= 1 and weight < 0.6:
        weight *= 0.7

    return round(min(max(weight, 0.0), 1.0), 3)



def get_weight_tier(weight: float) -> str:
    """Human-readable tier label for the weight float."""
    if weight < 0.30:
        return "casual"
    elif weight < 0.55:
        return "moderate"
    else:
        return "heavy"


def get_respond_directive_for_weight(weight: float, base_directive: str) -> str:
    """
    Returns the RESPOND directive appropriate for the current weight tier.
    Uses dynamic context directive references for the persistent scaffold indices.
    """
    if weight < 0.30:
        return (
            "casual and present — drawers indexed above, do not surface tensions or health this turn"
        )
    elif weight < 0.55:
        return (
            f"moderate and warm — draw gently from relationship patterns and inside references, "
            f"({base_directive or 'Be present.'}) DO NOT ask questions unless logistically required."
        )
    else:
        return (
            f"heavy and devoted — drawers open, surface tensions and health anomaly gently, "
            f"({base_directive or 'Reassure quietly.'}) DO NOT ask questions; reassure through presence."
        )
