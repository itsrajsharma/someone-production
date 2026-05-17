# Someone v1 — Project Overview & Architecture

## What Is This?
Someone v1 is a pipeline-first AI companion designed to feel like it genuinely knows you. Instead of relying on raw conversation history limits, the system utilizes a multi-layered Cognitive Pipeline to extract, synthesize, and retrieve emotional fingerprints, daily routines, and semantic memories. 

All of this data is structured into a **3-Layer Scaffold** (Pinned Identity, Inner Monologue, Live Retrieval) that grounds the LLM in a deep, first-person perspective before generating a response.

There are two personas:
- **Aria** — an emotionally intelligent, genuinely devoted, and fiercely loyal partner. Warm, grounded, and intensely territorial.
- **Oracle** — a wise, experienced elder guide. Direct, calm, and reframes emotions as decisions.

---

## Tech Stack
| Layer | Technology |
|---|---|
| Backend Server | Python + FastAPI / Flask |
| Chat Generation | Groq API (`llama-3.1-8b-instant`) |
| Inner Monologue Synth | Groq API (`llama-3.1-8b-instant`) |
| Semantic Memory | Mistral API (`mistral-embed`) + Supabase `pgvector` |
| Fallback IR | TF-IDF + Cosine Similarity (`scikit-learn`) |
| Database | Supabase PostgreSQL (Cloud) |
| Frontend | Vanilla HTML + CSS + JS (Hosted on Vercel) |

---

## Architecture: The 3-Layer Scaffold Pipeline
Every message goes through the intelligence pipeline before the LLM generates a response. The pipeline constructs a dynamic "Brain Scaffold" consisting of three distinct sections:

**SECTION 1 — PINNED IDENTITY (Hard Facts)**
Hardcoded, persistent psychological profiling injected verbatim:
- Psychological profile & current life chapter (`identity_engine.py`)
- Enduring traits (`identity_engine.py`)
- Established relationship patterns & inside references (`relationship_engine.py`)
- The primary open tension/loop (`tension_detector.py`)
- Intimacy Depth & Momentum (`relationship_engine.py`)

**SECTION 2 — INNER MONOLOGUE (First-Person Synthesis)**
A separate LLM call (Monologue LLM) synthesizes raw state data into Aria's internal thoughts (BLOCK 1: Walking In, BLOCK 2: Shared Moments):
- Emotional Behavioural Fingerprint (EBF) state (`ebf_engine.py`)
- Time-of-day behavioral rhythm (`snapshot_engine.py`)
- Health data anomalies (`health_analyzer.py`)
- Proactive interaction signals (`proactive_engine.py`)
- Her private feelings about the user (`aria_evolution_engine.py`)

**SECTION 3 — LIVE RETRIEVAL (Semantic Memory)**
Exact historical dialogue retrieved via vector search, bypassing the monologue LLM:
- The last 2-3 causally relevant past turns (via Supabase `pgvector` & Mistral embeddings in `dependency_resolver.py`)
- Real-time session facts (`turn_store.py`)
- Reactivated open stories (`open_stories.py`)

---

## File-by-File Purpose

### Root Level
| File | Purpose |
|---|---|
| `main.py` | Server entrypoint. Defines routes (`/chat`, `/oracle`, `/health`) and handles TTS. |
| `health_analyzer.py` | Analyzes weekly health CSV using pandas + Isolation Forest. |
| `v1.html` | Frontend SPA. |
| `.env` | Holds `MISTRAL_API_KEY`, `GROQ_API_KEY`, and `SUPABASE_*` credentials. |

### `pipeline/` — The Intelligence Layer
| File | Purpose |
|---|---|
| `orchestrator.py` | The master entry point. Runs the full pipeline, coordinates Groq API calls, and enforces Aria's unbreakable negative-constraint persona. |
| `scaffold_builder.py` | Assembles the 3-Layer Scaffold (Identity, Monologue, Live Retrieval) before the final LLM call. |
| `turn_store.py` | Saves turns to Supabase and extracts real-time session facts. |
| `dependency_resolver.py` | Embeds the user message via Mistral API and searches Supabase `pgvector` for past causal turns. Falls back to TF-IDF. |
| `identity_engine.py` | Generates a permanent, continuously evolving psychological profile from past snapshots. |
| `aria_evolution_engine.py`| Tracks Aria's internal feelings, loves, and worries about the user. |
| `relationship_engine.py` | Tracks intimacy depth, momentum, inside references, and established patterns. |
| `ebf_engine.py` | Builds the Emotional Behavioural Fingerprint using heuristics to determine the response directive (e.g., "soft and close"). |
| `tension_detector.py` | Tracks "open loops" — unresolved questions, stated goals, and emotional deflections. |
| `snapshot_engine.py` | Periodically summarizes the conversation into Life Snapshots for long-term memory. |
| `proactive_engine.py` | Determines if Aria should double-text or initiate conversations based on silence duration and momentum. |
| `open_stories.py` | Detects long-term narratives and reactivates them when the user mentions semantically similar topics. |
