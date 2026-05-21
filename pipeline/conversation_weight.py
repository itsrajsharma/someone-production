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
    last_bot_message: str = "",
) -> str:
    """
    Uses llama-3.1-8b-instant to classify the emotional/contextual weight of a message.
    Returns: 'casual', 'moderate', 'opening_up', or 'heavy'.
    """
    import os
    from openai import OpenAI

    prompt = f"""Classify this chat message's emotional weight. Reply with ONE word only: casual, moderate, opening_up, or heavy.

casual = greetings, banter, teasing, logistics ("hey", "don't lie", "what should we watch", "haha", "ok cool")
moderate = routine updates, mild feelings ("just got to office", "bit tired", "had a busy day")
opening_up = vulnerability, negations revealing distress ("actually no I'm not really", "not fine", "struggling lately")
heavy = crisis, fear, deep pain ("I'm scared", "I feel lost", "we had a big fight")

"anyway" + lightweight topic = casual. Short playful denials = casual. Negations like "not really"/"not fine" = opening_up.

Context: "{last_bot_message}"
Message: "{message}"
Weight:"""

    try:
        client = OpenAI(
            api_key=os.environ["GROQ_API_KEY"],
            base_url="https://api.groq.com/openai/v1",
        )
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=10,
        )
        result = response.choices[0].message.content.strip().lower()
        for category in ["casual", "moderate", "opening_up", "heavy"]:
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
) -> float:
    """
    Returns a float 0.0–1.0 representing conversation weight.
    First attempts to classify using llama-3.1-8b-instant.
    Falls back to python heuristics if the LLM call fails.
    """
    # 1. Attempt LLM classification
    category = classify_message_weight_llm(message, last_bot_message)
    
    if category != "fallback":
        mapping = {
            "casual": 0.15,
            "moderate": 0.40,
            "opening_up": 0.65,
            "heavy": 0.85
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
        return 0.85

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
    elif weight < 0.75:
        return "opening_up"
    else:
        return "heavy"


def get_respond_directive_for_weight(weight: float, base_directive: str) -> str:
    """
    Returns the RESPOND directive appropriate for the current weight tier.
    In casual mode this replaces the EBF-derived directive entirely.
    In heavier modes, the base_directive from EBF is used.
    """
    if weight < 0.30:
        return (
            "Be present and warm. Follow his lead completely. "
            "Do not surface concerns, do not project emotions onto him, do not diagnose or analyze. "
            "He's just talking. Be the person who's just here. DO NOT ask questions."
        )
    elif weight < 0.55:
        directive = base_directive or "Be present. Warm and easy. Let him set the tone."
        return f"{directive} DO NOT ask questions unless necessary. Make statements, stay close."
    else:
        # Heavy enough — use the full EBF-derived directive
        directive = base_directive or "Hold space. Say one true thing. Stay close."
        return f"{directive} DO NOT ask questions. Keep your responses grounded, make supportive statements, and do not interrogate him."
