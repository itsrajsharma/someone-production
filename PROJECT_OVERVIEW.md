# Someone v1 — Project Overview & Architecture

## What Is This?
Someone v1 is a pipeline-first AI companion designed to feel like it genuinely knows you. Instead of relying on raw conversation history limits, the system utilizes a multi-layered Cognitive Pipeline to extract, synthesize, and retrieve emotional fingerprints, daily routines, and semantic memories. The core philosophy is: **Conversation history is replaced by structured intelligence.**

There are two personas:
- **Aria** — an emotionally intelligent, genuinely devoted, and fiercely loyal partner. Warm, grounded, and intensely territorial.
- **Oracle** — a wise, experienced elder guide. Direct, calm, and reframes emotions as decisions.

---

## Tech Stack
| Layer | Technology |
|---|---|
| Backend Server | Python + FastAPI / Flask |
| Core Generation | Groq API (`llama-3.1-8b-instant`) |
| Semantic Memory | Mistral API (`mistral-embed`) + Supabase `pgvector` |
| Fallback IR | TF-IDF + Cosine Similarity (`scikit-learn`) |
| Database | Supabase PostgreSQL (Cloud) |
| Frontend | Vanilla HTML + CSS + JS (Hosted on Vercel) |

---

## The End-to-End Execution Flow

### PHASE 0 — LOGIN / SESSION START
Before the user sends any message, the frontend calls `generate_proactive_signal()`. This reads the relationship state, ebf, tensions, snapshots, rhythm, and health anomalies.
- If it finds an active signal (e.g. an open tension she's holding, a health concern), it passes a `proactive_signal` into the pipeline. Aria walks in already thinking about something.
- If no signal, she walks in present.

### PHASE 1 — PRE-RESPONSE
When the user sends a message, `run_pipeline()` executes sequentially:
1. **EBF Update (`update_ebf`)**: Reads the message, runs a small LLM classification to update current emotional state, unmet need, and trust level.
2. **Tension Resolution (`resolve_tensions`)**: Scans for resolution signals ("got it", "makes sense") and clears open loops *before* they pollute the scaffold.
3. **Open Story Detection (`detect_and_save_story`)**: Uses regex to catch narratives ("I've been dealing with...") and deduplicates them via TF-IDF against existing stories.
4. **Scaffold Build (`build_scaffold`)**: The grand assembler. Pulls from all engines, calls the Monologue LLM, and retrieves semantic memories via `dependency_resolver`.
5. **Model Call (`_call_groq`)**: The final LLM call using the strictly formatted 3-Layer Scaffold.

### PHASE 2 — POST-RESPONSE (Asynchronous)
Once the response is generated and sent to the user, the server runs heavy analytics in a non-blocking background thread:
1. **Save Turns**: Both user and assistant turns are saved, and transient session facts are extracted.
2. **Tension Detection (`detect_tensions`)**: Scans the user message for new questions, goals, or emotional deflections.
3. **Snapshot Trigger (`should_generate_snapshot`)**: Every **20 turns**, the pipeline updates long-term memory:
   - `generate_snapshot()`: Compresses the 20 turns into facts, events, and tones.
   - `update_rhythm()`: Aggregates time-of-day behavioral patterns.
   - `update_relationship_state()`: Updates intimacy depth, momentum, and inside jokes.
   - `update_aria_self()`: Updates what she loves, worries about, and wants to know.
   - `update_identity_if_needed()`: Updates core psychological profile (every 2 snapshots).

---

## Architecture: The 3-Layer Scaffold

The `build_scaffold()` method builds the prompt injected into the LLM context. It strictly enforces token economy and context grounding.

### SECTION 1 — PINNED IDENTITY (Hard Facts)
Pure Python string assembly. No LLM summarization. Data is aggressively capped to prevent bloat.
* **LAYER A — Core Identity**: Psychological profile, life chapter, traits.
* **LAYER B — How He Is Right Now**: EBF state, trust float, energy, unmet need.
* **LAYER C — How He Moves Through Time**: Trust growth rate, most open time, current time-of-day rhythm. *(Tiered Consolidation logic planned)*
* **LAYER D — What Sits Between Them**: Intimacy depth, momentum, inside references (capped), what she loves/worries about him (capped).
* **LAYER E — What's Unfinished**: Open tensions (capped at 5), Active open stories (capped at 4), and health anomalies.
*Ends with `RESPOND: {respond_directive}`.*

### SECTION 2 — INNER MONOLOGUE (Emotional Synthesis)
A separate LLM call (`_synthesize_inner_monologue`) runs before Section 3. It strips away all hard facts and focuses purely on emotional texture.
* **BLOCK 1 — Walking In**: Her raw, private thoughts walking into the conversation (synthesizes her unmet need, proactive signal, health worries, and time gap).
* **BLOCK 2 — Shared Moments**: 3-4 warm, first-person memories sampled randomly from past snapshots and established patterns.

### SECTION 3 — LIVE RETRIEVAL (Semantic Memory)
Exact historical dialogue retrieved via vector search, bypassing the monologue LLM.
* **LAST DECISION**: The bot's last turn (truncated to 120 chars).
* **CURRENT INTENT**: Intent extracted from the current message.
* **OLDER MEMORY**: The top causally relevant past turns retrieved via Mistral + Supabase `pgvector`. Labeled with `[CAUSAL PAST TURNS SURFACED FOR RELEVANCE]`.
* **REACTIVATED STORY**: Any open story touched upon in the current message.

---

## Memory Compression Strategies

To prevent infinite context bloat over months of usage, the pipeline uses three distinct memory pruning strategies:

1. **State Resolution**: Open Tensions and Open Stories are cleared or marked dormant the moment they are resolved.
2. **List Capping**: Array data in `relationship_engine` and `aria_evolution_engine` (e.g., inside references, established patterns) are actively pruned. The LLM is instructed to merge stale items and output a strict maximum of 5 items. `scaffold_builder.py` enforces a secondary truncate.
3. **Tiered Consolidation (Upcoming)**: Time-series data like snapshots and behavioural rhythms will be stored in three tiers:
   - *Tier 1 (Raw)*: Last 5 unedited sessions.
   - *Tier 2 (Weekly)*: LLM-consolidated summaries of the last 3 weeks.
   - *Tier 3 (Monthly)*: LLM-consolidated summaries of everything older. 
   *(This ensures chronological context without infinite array growth).*
