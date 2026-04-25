# Someone v1 — Project Overview

## What Is This?


Someone v1 is a pipeline-first AI companion designed to feel like it genuinely knows you — not by reading thousands of tokens of chat history on every message, but by maintaining structured, evolving memory about who you are. The system tracks your emotional state, communication patterns, unresolved life tensions, and open personal narratives across sessions, compressing all of it into a tight context scaffold that the model receives instead of raw history. The result is two distinct AI personas — Aria (an emotionally intelligent close friend) and Oracle (a reframing elder guide) — that respond with awareness of your long-term arc, not just your last message.
Every user message passes through six sequential intelligence layers before any LLM call is made: an EBF Engine that updates your Emotional Behavioural Fingerprint (arousal, trust, communication style, unmet needs — all via heuristics, zero ML), a Tension Resolver that tracks and closes unresolved emotional loops, an Open Story Detector that identifies and reactivates long-running personal narratives, a Dependency Resolver that retrieves the 2–3 past turns most causally relevant to the current message, a Snapshot Engine that generates structured long-term memory every ~10 turns, and finally a Scaffold Builder that compresses all of this into an ~80-token context block injected into the LLM prompt — replacing full history and cutting token cost by ~70%.
The stack includes Python and Flask for the backend, Mistral AI (devstral-2512 via Conversations API) as the LLM, SentenceTransformers (all-MiniLM-L6-v2) with ChromaDB for primary semantic retrieval, TF-IDF cosine similarity as a retrieval fallback, Isolation Forest (scikit-learn) for anomaly detection on user-uploaded health CSVs, pandas for time-series health analysis, Microsoft Edge TTS for voice output, and a vanilla HTML/CSS/JS frontend with real-time SVG data visualization and async chat UI — with all state persisted in flat JSON files, no database.

**Someone v1** is a pipeline-first AI companion chatbot. The core idea is that instead of passing raw conversation history into an LLM, every user message gets processed through a layered intelligence pipeline that extracts emotional state, causal context, unresolved tensions, open life stories, and behavioral patterns — then compresses all of that into a tight ~80-token "scaffold" that the model receives alongside the message.

The result is a system where the AI feels like it *actually knows you* — not because it reads thousands of tokens of chat history every time, but because it maintains structured memory about who you are, how you feel, what you haven't resolved yet, and how you communicate.

There are two personas in the app:

- **Aria** — your emotionally intelligent close friend. Warm, grounded, honest, with a touch of humour. She validates you without enabling self-pity and pushes growth without being preachy.
- **Oracle** — a wise, experienced elder guide. Direct, calm, and reframes emotions as decisions. He sees the long arc and doesn't do emotional mirroring.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend / API | Python + Flask |
| LLM | Mistral AI (`devstral-2512` via beta Conversations API) |
| Semantic Search | Sentence Transformers (`all-MiniLM-L6-v2`) + ChromaDB |
| Fallback IR | TF-IDF + Cosine Similarity (`scikit-learn`) |
| Anomaly Detection | Isolation Forest (`scikit-learn`) |
| Health Data | pandas (CSV ingestion + analysis) |
| Text-to-Speech | Microsoft Edge TTS (`edge-tts`) |
| Frontend | Vanilla HTML + CSS + JS (`v1.html`) |
| Environment | Python `dotenv` |
| Cross-Origin | `flask-cors` |
| Data Storage | JSON flat files (no database) |

---

## Architecture: The Pipeline

Every message to Aria goes through this flow before the LLM is ever called:

```
User Message
     │
     ▼
 [EBF Engine]          ← Update emotional/behavioural fingerprint
     │
     ▼
 [Tension Resolver]    ← Resolve previously open loops if user signals closure
     │
     ▼
 [Open Story Detector] ← Check if message starts a new life narrative
     │
     ▼
 [Scaffold Builder]    ← Pull from all layers → compress into ~80-token context
     │
     ├── Dependency Resolver   (retrieve causally relevant past turns)
     ├── EBF Summary           (emotional tone, energy, communication style)
     ├── Tension Loop          (most recent unresolved open question/goal)
     ├── Open Story Reactivation (does this message relate to an old story?)
     ├── Snapshot Facts        (long-term facts extracted every 10 turns)
     ├── Session Facts         (real-time in-memory facts this session)
     └── Health Context        (sleep/stress data if CSV uploaded)
     │
     ▼
 [Mistral API Call]    ← Aria responds with scaffold as instructions
     │
     ▼
 [Post-processing]
     ├── Save turn (user + assistant) with causal tags
     ├── Detect new tensions from user message
     └── Every ~10 turns: generate Life Snapshot → update Behaviour Rhythm
```

---

## File-by-File Purpose

### Root Level

| File | Purpose |
|---|---|
| `main.py` | Flask server entrypoint. Defines routes: `/chat` (Aria), `/oracle` (Oracle), `/health` (CSV upload), `/status` (state check). Handles TTS via edge-tts. |
| `health_analyzer.py` | Analyzes weekly health CSV using pandas + Isolation Forest. Returns avg sleep, avg stress, weekly trend, and anomaly days. Also supports multi-week monthly aggregation. |
| `v1.html` | Full single-page frontend. Chat UI for both Aria and Oracle. Handles CSV upload, audio playback, and health chart rendering. |
| `tts.py` | Standalone TTS script (early version/utility). |
| `main.ipynb` | Jupyter notebook, likely used for early prototyping/experimentation. |
| `.env` | Holds the `MISTRAL_API_KEY`. |
| `.gitignore` | Ignores virtual env, pycache, local data files. |

### `pipeline/` — The Intelligence Layer

| File | Layer | Purpose |
|---|---|---|
| `orchestrator.py` | Master | The single entry point called by Flask. Runs the full pipeline in order: EBF update → tension resolve → story detect → scaffold build → Mistral call → turn save → tension detect → snapshot check. Also holds Aria's system prompt. |
| `turn_store.py` | Layer 1 | Stores every conversation turn as a JSON record with causal tags (topics, entities, intent, emotion valence). Also runs `extract_session_facts()` to capture real-time facts like relationships, plans, and corrections from user messages. |
| `dependency_resolver.py` | Layer 1 | Given the current user message, finds the 2–3 past turns most causally related to it. Primarily uses SentenceTransformers + ChromaDB (semantic search). Falls back to TF-IDF cosine similarity if ChromaDB is unavailable. |
| `tension_detector.py` | Layer 2 | Tracks "open loops" — unresolved questions, stated goals, and emotional deflections. Detects them on each message and marks them resolved when the user signals closure (e.g., "that makes sense", "got it"). |
| `ebf_engine.py` | Layer 3 | Builds the Emotional Behavioural Fingerprint (EBF). Detects arousal level from punctuation/caps, communication style (formal/informal/direct), emotional state from keywords, unmet needs, and response preferences. Updates trust level incrementally. All done with zero ML — pure regex/heuristics. |
| `open_stories.py` | Layer 4 | Tracks unfinished life narratives: relationships, conflicts, dreams, projects. Detects them from trigger patterns and reactivates them when a new message is semantically similar (TF-IDF cosine similarity). |
| `snapshot_engine.py` | Layer 4 | Every ~10 turns, generates a "Life Snapshot" — a structured summary of facts learned, dominant emotional tone, notable events, and open stories. These snapshots form the long-term memory. |
| `behaviour_rhythm.py` | Layer 4 | Aggregates snapshot history into a Behavioural Rhythm Profile: when the user is most open (by time of day), trust growth rate, and storytelling frequency. |
| `scaffold_builder.py` | Output Layer | Assembles all pipeline outputs into the final compressed prompt scaffold (~80 tokens). Pulls: recent turns, older relevant memory, last bot response, current intent, facts, session facts, open loops, story reactivation, health data, EBF state, and RESPOND directive. |
| `oracle_scaffold_builder.py` | Oracle Layer | Builds a simpler scaffold for Oracle — pulls long-term facts, snapshot events, rhythm profile, health data, and the top open tension. Formatted for Oracle's decision-focused, emotionless style. |
| `__init__.py` | Package | Package marker. |

### `data/` — Persistent State

| File | Contents |
|---|---|
| `turns.json` | All conversation turns with causal tags |
| `ebf.json` | Current Emotional Behavioural Fingerprint |
| `tensions.json` | Open and resolved tension loops |
| `open_stories.json` | Detected life narratives (open/resolved) |
| `snapshots.json` | Life snapshots (one per ~10 turns) |
| `rhythm.json` | Behavioural rhythm profile over all snapshots |
| `health_report.json` | Most recent weekly health analysis (from CSV upload) |
| `oracle_turns.json` | Oracle conversation history |
| `latest_upload.csv` | Most recently uploaded health CSV |
| `chroma/` | ChromaDB vector store (turn embeddings, auto-generated) |

---

## Key Design Decisions

- **No full history in context:** The LLM never sees raw chat logs. Only the compressed ~80-token scaffold is passed in the `instructions` field. This keeps costs low and prevents context bloat.
- **Layered memory without an LLM:** All tagging, fact extraction, emotion detection, and tension tracking is done with heuristics/regex — not an LLM. Only the final response generation uses Mistral.
- **Two separate personas with shared awareness:** Aria and Oracle are independent models with different scaffolds, tones, and purposes. They are aware of each other's existence but don't share memory or conversations.
- **Flat JSON storage:** No database. All state lives in `data/*.json` files. Simple, portable, and easy to inspect/debug.
- **Health as relational context:** CSV health data is injected directly into Aria and Oracle's scaffolds so they can respond contextually to the user's actual physical state.
