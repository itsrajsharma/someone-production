"""
LLM Client Factory
==================
Single source of truth for all LLM API calls in the pipeline.

Routes everything through FreeLLMAPI — a local OpenAI-compatible proxy
that aggregates free tiers from Groq, Google, Cerebras, SambaNova, Mistral,
OpenRouter, Cohere, HuggingFace, NVIDIA, and more.

FreeLLMAPI: https://github.com/tashfeenahmed/freellmapi
Start it:   npm run dev  (in the freellmapi directory, serves API on :3001)

WHY "auto":
    Every provider has TPM/RPM/TPD limits. Hitting one used to crash the
    whole pipeline (the original 10k token burst problem on Groq 8B).
    FreeLLMAPI solves this transparently:
      - tracks per-key usage across all providers
      - on 429 / rate limit / token exhaustion, router immediately
        falls over to the next model in the fallback chain (up to 20 tries)
      - sticky sessions keep multi-turn conversations on the same model
        for 30 minutes to avoid mid-conversation model switches
    Using "auto" lets the router + fallback chain handle all of this.
    The fallback chain order is set in the dashboard at localhost:5173.

    If you want to force a specific model (e.g. for testing), override:
      FREELLM_MAIN_MODEL=mistral-large-latest
      FREELLM_FAST_MODEL=llama-3.1-8b-instant

NOTE: FreeLLMAPI does NOT support /v1/embeddings.
      dependency_resolver.py keeps its direct Mistral embed calls.

Config (.env):
    FREELLM_BASE_URL=http://localhost:3001/v1
    FREELLM_KEY=freellmapi-...
"""

import os
from openai import OpenAI


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
    (client, model) for fast background classification tasks.
    EBF, weight classification, snapshot, identity, rhythm,
    session facts, relationship engine, aria evolution, proactive.

    Defaults to "auto" — router picks the fastest healthy model.
    Override with FREELLM_FAST_MODEL in .env if needed.
    """
    model = os.environ.get("FREELLM_FAST_MODEL", "auto")
    return _get_client(), model


def get_main_client() -> tuple[OpenAI, str]:
    """
    (client, model) for Aria's main voice generation.
    Orchestrator chat, monologue synthesis, intro, Oracle.

    Defaults to "auto" — router picks the best healthy model.
    Override with FREELLM_MAIN_MODEL in .env if needed.
    """
    model = os.environ.get("FREELLM_MAIN_MODEL", "auto")
    return _get_client(), model
