"""
LLM Client Factory with Manual Fallback Handling
================================================
Routes all LLM calls directly to OpenRouter (https://openrouter.ai),
an OpenAI-compatible API aggregator with free and paid model access.

Instead of relying on a single model, we explicitly define Python-level
fallback chains for each tier (FAST, MAIN, HEAVY).

If a model throws an error (403, 429, 5xx), the wrapper catches it
and immediately tries the next model in the list.
"""

import os
import time
from openai import OpenAI

# ── PREDEFINED FALLBACK CHAINS ──────────────────────────────────────────
# Model IDs are OpenRouter slugs. Free-tier models (:free) require no credits.
# Verified free models available on this key (from /api/v1/models query):
#   meta-llama/llama-3.3-70b-instruct:free   — best free MAIN model
#   meta-llama/llama-3.2-3b-instruct:free    — smallest/fastest free
#   google/gemma-4-31b-it:free               — Google, good quality
#   google/gemma-4-26b-a4b-it:free           — Google MoE variant
#   qwen/qwen3-next-80b-a3b-instruct:free    — Qwen, excellent quality
#   qwen/qwen3-coder:free                    — Qwen coder variant
#   nousresearch/hermes-3-llama-3.1-405b:free — huge, best free heavy
#   nvidia/nemotron-3-super-120b-a12b:free   — Nvidia, strong heavy
#   nvidia/nemotron-3-nano-30b-a3b:free      — Nvidia fast/small
#   nvidia/nemotron-nano-9b-v2:free          — fastest Nvidia
#   nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free — reasoning
#   poolside/laguna-m.1:free                 — good general
#   poolside/laguna-xs-2.1:free             — small/fast
#   nvidia/nemotron-3-ultra-550b-a55b:free   — very large
#   openai/gpt-oss-20b:free                  — OpenAI OSS small
#   tencent/hy3:free                         — Tencent Hunyuan
#   cohere/north-mini-code:free              — Cohere mini
#   cognitivecomputations/dolphin-mistral-24b-venice-edition:free

# Fast tier: for classification, tagging, inner monologue. Speed is king.
FAST_MODELS = [
    # Verified free on OpenRouter (no credits needed)
    "meta-llama/llama-3.2-3b-instruct:free",        # smallest, fastest
    "openai/gpt-oss-20b:free",                       # OpenAI OSS small
    "nvidia/nemotron-nano-9b-v2:free",               # fast Nvidia
    "nvidia/nemotron-3-nano-30b-a3b:free",           # slightly bigger
    "poolside/laguna-xs-2.1:free",                   # good small model
    "google/gemma-4-31b-it:free",                    # Google quality
    "google/gemma-4-26b-a4b-it:free",               # Google MoE
    "cohere/north-mini-code:free",                   # Cohere mini
    "tencent/hy3:free",                              # Tencent fallback
    "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
    "meta-llama/llama-3.3-70b-instruct:free",        # heavyweight fallback
]

# Main tier: for Aria's actual dialogue. Needs high intelligence + decent speed.
MAIN_MODELS = [
    # Verified free on OpenRouter (no credits needed)
    "meta-llama/llama-3.3-70b-instruct:free",        # best free general model
    "qwen/qwen3-next-80b-a3b-instruct:free",         # excellent reasoning
    "google/gemma-4-31b-it:free",                    # Google, clean outputs
    "google/gemma-4-26b-a4b-it:free",               # Google MoE
    "poolside/laguna-m.1:free",                      # medium quality
    "nousresearch/hermes-3-llama-3.1-405b:free",    # huge, best free
    "nvidia/nemotron-3-super-120b-a12b:free",        # Nvidia large
    "nvidia/nemotron-3-ultra-550b-a55b:free",        # Nvidia ultra
    "nvidia/nemotron-3-nano-30b-a3b:free",           # smaller Nvidia fallback
    "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
    "meta-llama/llama-3.2-3b-instruct:free",         # last resort tiny
]

# Heavy tier: for deep context after 10+ turns. Quality over speed.
HEAVY_MODELS = [
    # Verified free on OpenRouter (no credits needed)
    "nvidia/nemotron-3-ultra-550b-a55b:free",        # largest free model
    "nousresearch/hermes-3-llama-3.1-405b:free",    # 405B hermes
    "nvidia/nemotron-3-super-120b-a12b:free",        # 120B Nvidia
    "qwen/qwen3-coder:free",                         # Qwen coder (strong reasoning)
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",  # reasoning model
    "qwen/qwen3-next-80b-a3b-instruct:free",         # 80B Qwen
    "meta-llama/llama-3.3-70b-instruct:free",        # reliable 70B
    "google/gemma-4-31b-it:free",                    # Google fallback
    "nvidia/nemotron-3-nano-30b-a3b:free",           # smaller fallback
    "poolside/laguna-m.1:free",                      # last resort
]


def _get_raw_client() -> OpenAI:
    """Return an OpenAI-compatible client pointed directly at OpenRouter."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set.\n"
            "Add to .env:  OPENROUTER_API_KEY=sk-or-v1-xxxx\n"
            "Get a free key at https://openrouter.ai"
        )
    return OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers={
            "HTTP-Referer": "https://someone-production.vercel.app",
            "X-Title": "Someone v1 - Aria",
        },
    )


class FallbackCompletions:
    def __init__(self, fallback_list: list[str]):
        self.fallback_list = fallback_list
        self._client = None  # lazy — initialised on first use

    def _ensure_client(self):
        if self._client is None:
            self._client = _get_raw_client()

    def create(self, *args, **kwargs):
        # Initialise client on first call — so a missing API key raises here
        # (inside the FastAPI request handler) rather than at wrapper construction,
        # which would crash the ASGI middleware stack with an unhandled exception.
        self._ensure_client()

        # Ignore whatever model string the caller passed — enforce our fallback list.
        kwargs.pop("model", None)

        last_err = None
        for model in self.fallback_list:
            try:
                return self._client.chat.completions.create(model=model, *args, **kwargs)
            except Exception as e:
                print(f"  [LLM Fallback] {model} failed: {e}. Trying next...")
                last_err = e
                time.sleep(0.5)  # slight backoff before next attempt

        raise RuntimeError(f"All fallback models failed. Last error: {last_err}")


class FallbackChat:
    def __init__(self, fallback_list: list[str]):
        self.completions = FallbackCompletions(fallback_list)


class FallbackClientWrapper:
    """
    Duck-types an OpenAI client but routes chat.completions.create
    through a hardcoded list of fallback models.
    The underlying OpenAI client is created lazily on first use.
    """
    def __init__(self, fallback_list: list[str]):
        self.chat = FallbackChat(fallback_list)


def get_fast_client() -> tuple[FallbackClientWrapper, str]:
    """
    Returns (wrapper_client, 'ignored').
    For fast classification tasks (EBF, rhythm, facts, tags, monologue).
    """
    return FallbackClientWrapper(FAST_MODELS), "ignored"


def get_main_client() -> tuple[FallbackClientWrapper, str]:
    """
    Returns (wrapper_client, 'ignored').
    For standard chat turns (Aria's actual response).
    """
    return FallbackClientWrapper(MAIN_MODELS), "ignored"


def get_heavy_client() -> tuple[FallbackClientWrapper, str]:
    """
    Returns (wrapper_client, 'ignored').
    For deep context turns (e.g. session > 10 turns).
    """
    return FallbackClientWrapper(HEAVY_MODELS), "ignored"

