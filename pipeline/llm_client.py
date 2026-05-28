"""
LLM Client Factory
==================
Single source of truth for all LLM API calls in the pipeline.

Routes everything through FreeLLMAPI — a local OpenAI-compatible proxy
that aggregates free tiers from Groq, Google, Cerebras, SambaNova, etc.
behind a single /v1/chat/completions endpoint with automatic fallover.

FreeLLMAPI: https://github.com/tashfeenahmed/freellmapi
Start it:   npm run dev          (dev — serves on :5173 UI + :3001 API)
            node server/dist/index.js  (prod — both on :3001)

Config (add to .env):
    FREELLM_BASE_URL=http://localhost:3001/v1
    FREELLM_KEY=freellmapi-xxxxxxxxxxxxxxxx

Note: FreeLLMAPI does NOT support /v1/embeddings.
      dependency_resolver.py keeps its direct Mistral embed calls.

Model tiers:
    MAIN_MODEL  — Aria's voice, monologue, Oracle. Needs quality.
                  Default: "llama-3.3-70b-versatile"
                  FreeLLMAPI routes to Groq first; falls over to
                  SambaNova Llama 4 / Gemini 2.5 Flash etc. on 429.

    FAST_MODEL  — All background classification (EBF, weight, snapshot,
                  identity, rhythm, session facts, etc.). Speed > quality.
                  Default: "auto"  — router picks fastest available.
"""

import os
from openai import OpenAI

_DEFAULT_MAIN_MODEL = "llama-3.3-70b-versatile"
_DEFAULT_FAST_MODEL = "auto"


def _get_client() -> OpenAI:
    """Return an OpenAI client pointed at the local FreeLLMAPI proxy."""
    base_url = os.environ.get("FREELLM_BASE_URL", "http://localhost:3001/v1")
    api_key = os.environ.get("FREELLM_KEY", "")
    if not api_key:
        raise RuntimeError(
            "FREELLM_KEY is not set.\n"
            "1. Start FreeLLMAPI: npm run dev  (in the freellmapi directory)\n"
            "2. Open http://localhost:5173, add your provider keys\n"
            "3. Copy the unified freellmapi-... key from the dashboard\n"
            "4. Add to .env:  FREELLM_KEY=freellmapi-xxxxxxxxxxxxxxxx"
        )
    return OpenAI(api_key=api_key, base_url=base_url)


def get_fast_client() -> tuple[OpenAI, str]:
    """
    (client, model) for fast background tasks.
    EBF, weight classification, snapshot, identity, rhythm,
    session facts, relationship engine, aria evolution, proactive.
    """
    model = os.environ.get("FREELLM_FAST_MODEL", _DEFAULT_FAST_MODEL)
    return _get_client(), model


def get_main_client() -> tuple[OpenAI, str]:
    """
    (client, model) for Aria's main voice generation.
    Orchestrator chat, monologue synthesis, intro, Oracle.
    """
    model = os.environ.get("FREELLM_MAIN_MODEL", _DEFAULT_MAIN_MODEL)
    return _get_client(), model
