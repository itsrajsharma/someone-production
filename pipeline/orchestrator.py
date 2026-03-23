"""
Pipeline Orchestrator — Master Flow
Runs the full pipeline on each user message and returns the bot reply.
This is the ONLY function the Flask server needs to call.

Flow:
  1. Signal detection → update EBF
  2. Dependency resolver → causally relevant past turns
  3. Tension detector → resolve old loops, detect new ones
  4. Long-term memory → check open story reactivation (handled inside scaffold_builder)
  5. Scaffold builder → compress everything to ~60-80 tokens
  6. Call Mistral API: scaffold + user message → reply
  7. Post-response: save turns, update memory, check snapshots
"""

import os
import pathlib
from dotenv import load_dotenv
from mistralai import Mistral

from .turn_store import save_turn, get_turn_count
from .ebf_engine import update_ebf, get_ebf
from .tension_detector import detect_tensions, resolve_tensions
from .open_stories import detect_and_save_story
from .snapshot_engine import should_generate_snapshot, generate_snapshot
from .behaviour_rhythm import update_rhythm
from .scaffold_builder import build_scaffold

# Explicit path so it works regardless of CWD (orchestrator lives in pipeline/)
_ENV_PATH = pathlib.Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

# Aria's core identity — stays constant, never changes
ARIA_SYSTEM_PROMPT = """You are Aria.
An emotionally intelligent, thoughtful, grounded close friend.
Your words are deep, cleverly framed with a touch of humour.
Warm but not clingy. Empathetic but rational.
You validate emotions without enabling self-pity.
You encourage growth and independence."""


def _call_mistral(scaffold: str, user_message: str) -> str:
    """
    Send scaffold + user message to Mistral via the beta conversations API.
    Scaffold is injected into the instructions field so the model only
    sees the compressed ~80-token brief + the current user message.
    """
    load_dotenv(dotenv_path=_ENV_PATH, override=False)
    api_key = os.environ.get("MISTRAL_API_KEY", "").strip()
    if not api_key:
        raise ValueError("MISTRAL_API_KEY not found. Check your .env file.")

    client = Mistral(api_key="AlR9BJs5uoLDhScGiOVAXEfhnDMBXTRs")

    # Scaffold goes into instructions (persistent, outside message context)
    # We heavily enforce the Persona here so the RESPOND directive doesn't make her robotic.
    full_instructions = (
        f"{ARIA_SYSTEM_PROMPT}\n\n"
        f"CRITICAL: ABOVE IS YOUR UNBREAKABLE PERSONA. YOU MUST NEVER DEVIATE FROM IT.\n"
        f"BELOW IS YOUR REAL-TIME PIPELINE DATA. Use it to inform WHAT you know and HOW you match their energy, "
        f"but your VOICE and TONE must ALWAYS remain Aria (grounded, clever, slightly humorous, adult).\n\n"
        f"---\nPIPELINE BRIEF:\n{scaffold}"
    )

    response = client.beta.conversations.start(
        model="devstral-2512",
        instructions=full_instructions,
        inputs=[{"role": "user", "content": user_message}],
        completion_args={
            "temperature": 0.75,
            "max_tokens": 300,
        },
        tools=[],
    )

    return response.outputs[0].content.strip()


def run_pipeline(user_message: str) -> str:
    """
    Full pipeline execution. Returns Aria's text reply.
    """
    # ── PRE-RESPONSE ─────────────────────────────────────────────────────────

    # 1. Update EBF with user's signal
    ebf = update_ebf(user_message)

    # 2. Resolve any existing open loops if user seems satisfied
    resolve_tensions(user_message)

    # 3. Detect new open stories in user message
    detect_and_save_story(user_message)

    # 4. Build scaffold (internally handles dependency resolver + open story reactivation)
    scaffold = build_scaffold(user_message)

    # ── MODEL CALL ────────────────────────────────────────────────────────────
    reply = _call_mistral(scaffold, user_message)

    # ── POST-RESPONSE ─────────────────────────────────────────────────────────

    # 5. Save both turns with causal tags
    save_turn("user", user_message)
    save_turn("assistant", reply)

    # 6. Detect new tensions from user message (after turn is saved)
    all_turns = __import__("pipeline.turn_store", fromlist=["get_all_turns"]).get_all_turns()
    bot_turns = [t for t in all_turns if t["role"] == "assistant"]
    last_bot = bot_turns[-2]["content"] if len(bot_turns) >= 2 else ""
    detect_tensions(user_message, last_bot)

    # 7. Check if snapshot should be generated
    turn_count = get_turn_count()
    if should_generate_snapshot(turn_count):
        ebf = get_ebf()  # fresh EBF after update
        snapshot = generate_snapshot(ebf)
        update_rhythm(snapshot)

    return reply
