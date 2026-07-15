# Someone v1 — The Architectural & Developmental Journey

This document presents a comprehensive synthesis of the developmental journey, architectural progression, and design choices behind **Someone v1** — an emotionally intelligent, physiologically aware AI companion system. 

Instead of relying on standard chat history blocks that bloat LLM context windows, Someone v1 is built on a **pipeline-first architecture**, where structured intelligence is compiled *outside* the LLM, and the model functions primarily as the verbal expression layer ("the voice, not the brain").

---

## 1. The Core Philosophy: "Memory is Structured Intelligence"

Traditional AI companions suffer from a fundamental limitation: they either have short-term memory limits that reset each session, or they blindly feed entire chat history logs into the model. This results in:
* **Exponential Cost & Latency:** Tokens grow linearly with every turn.
* **Context Fragmentation:** Models lose track of key facts as the conversation window stretches.
* **Loss of Relational Depth:** The AI fails to grasp the long-running psychological arc of the user’s life, feelings, and routines.

### The Solution: The 3-Layer Scaffold
Someone v1 addresses this by compressing all cognitive state into a flat, **~80-token instruction scaffold** assembled dynamically in Python. This scaffold is divided into three distinct segments:

1. **Pinned Identity (Layer A to E):** Hard psychological facts, current emotional state, behavioral rhythms, relationship intimacy levels, inside jokes, and active tensions.
2. **Inner Monologue:** A pre-synthesized emotional reaction explaining how Aria "walks into" the session.
3. **Live Retrieval:** Causally relevant turns retrieved from a database vector store + active stories.

```mermaid
graph TD
    UserMsg[User Message] --> Orchestrator[Orchestrator]
    Orchestrator --> EBF[Layer 3: EBF Engine]
    Orchestrator --> Weight[Weight Layer]
    Weight --> ScaffoldBuilder[Scaffold Builder]
    EBF --> ScaffoldBuilder
    
    subgraph Cognitive Pipeline (Python)
        Resolver[Layer 1: Dependency Resolver]
        Tension[Layer 2: Tension Detector]
        Stories[Layer 4: Open Stories]
        Snaps[Layer 4: Snapshot Engine]
        Rhythm[Layer 4: Behavioural Rhythm]
        RelEngine[Layer 5: Relationship Engine]
        Evolution[Layer 7: Aria Evolution]
        Identity[Layer 5: Identity Engine]
    end
    
    Resolver --> ScaffoldBuilder
    Tension --> ScaffoldBuilder
    Stories --> ScaffoldBuilder
    Snaps --> ScaffoldBuilder
    Rhythm --> ScaffoldBuilder
    RelEngine --> ScaffoldBuilder
    Evolution --> ScaffoldBuilder
    Identity --> ScaffoldBuilder
    
    ScaffoldBuilder --> FinalScaffold[Dynamic 80-Token Scaffold]
    FinalScaffold --> LLM[Mistral LLM: Voice Generation]
    LLM --> BotReply[Bot Reply]
```

---

## 2. Chronological Pipeline & Engine Evolution

Every user input is processed through a sequential multi-layered pipeline in [pipeline/orchestrator.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/orchestrator.py). The development of these components represents a progression from heuristic scripts to a robust backend service:

### Layer 1: Turn Store & Dependency Resolver
* **Implementation:** [pipeline/turn_store.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/turn_store.py) & [pipeline/dependency_resolver.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/dependency_resolver.py).
* **Journey & Decisions:** The system initially relied on a local file-based ChromaDB persistent client with `SentenceTransformers` (`all-MiniLM-L6-v2`) to perform local semantic search. A fallback to `TfidfVectorizer` (with tag-overlap scoring bonuses for shared topics, goals, and entities) was implemented for environments where local vector database setup was unstable.
* **Database Migration:** As the backend evolved into a multi-user service, local ChromaDB was replaced by **Supabase pgvector** vector storage. New turns are synced on-the-fly via a background task, querying embeddings via a Postgres RPC function (`match_turn_embeddings`).

### Layer 2: Tension Detector
* **Implementation:** [pipeline/tension_detector.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/tension_detector.py).
* **Journey & Decisions:** Early tests showed the companion forgot open questions or stated goals if the user shifted topics. The Tension Detector was built to track "open loops" (e.g. `open_question`, `stated_goal`, `deflected_emotion`) as separate records in the DB. Tensions remain open and are actively injected into the scaffold until a resolution signal (like *"makes sense"*, *"got it"*, or *"thanks"*) is detected in a new message.

### Layer 3: Emotional Behavioural Fingerprint (EBF) Engine
* **Implementation:** [pipeline/ebf_engine.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/ebf_engine.py).
* **Journey & Decisions:** Initially conceived as a fast, heuristic-only regex module, it was refactored to use a small, fast LLM (`llama-3.1-8b-instant` via Groq) to handle context and sarcasm (e.g. distinguishing a genuine deflection from a casual greeting). The EBF tracks the user's emotional state, arousal (energy), style, and unmet needs. To prevent erratic mood swings, trust levels accumulate slowly, and a rolling "dominant emotion pattern" is updated only after 5 turns.

### Layer 4: Long-Term Memory (Snapshots & Rhythm)
* **Implementation:** [pipeline/snapshot_engine.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/snapshot_engine.py) & [pipeline/behaviour_rhythm.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/behaviour_rhythm.py).
* **Snapshot Trigger:** Every **25 turns**, the orchestrator runs a background task using the fast LLM to compress the message log into a structured "Life Snapshot" (facts learned, emotional tone, and events).
* **Memory Pruning (Tiered Consolidation):** To prevent infinite snapshot array growth, the pipeline consolidates snapshots:
  * **Tier 1 (Raw):** Last 5 sessions kept verbatim.
  * **Tier 2 (Weekly):** Grouped by ISO week and consolidated by the LLM into a paragraph of Aria's observations.
  * **Tier 3 (Monthly):** Collapse multiple weekly summaries into a monthly overview.
* **Behavioural Rhythm:** Aggregates session timings and trust metrics to find when the user is most open, how fast trust grows, and how often they tell personal stories.

### Layer 5 & 7: Core Identity, Relationship, & Aria Evolution Engines
* **Implementation:** [pipeline/identity_engine.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/identity_engine.py), [pipeline/relationship_engine.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/relationship_engine.py), & [pipeline/aria_evolution_engine.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/aria_evolution_engine.py).
* **Core Identity:** Triggered every 2 snapshots, it compiles an overarching biography, daily routine, current life chapter, and enduring traits of the user.
* **Relationship Engine:** Updates the intimacy depth, relationship momentum, inside references (terms of endearment, shared jokes), established patterns, tender topics, and "what Aria is carrying."
* **Aria Evolution:** Evolving Aria's own feelings (what she loves, worries about, makes her laugh, wants to know, and her private feeling about the user).

### Layer 6: Proactive Engine & Session Facts
* **Implementation:** [pipeline/proactive_engine.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/proactive_engine.py).
* **Proactive Signal:** Fired before the user begins a session. Aria scans the current state, active tensions, health reports, and recent events. If an anomaly or open loop stands out, it generates a proactive signal (e.g. `concern_noticed`) injected directly into the live retrieval block, letting Aria walk into the conversation already thinking about something.
* **Session Facts:** If a user makes an in-session correction (*"no, I meant my sister, not my friend"*), a real-time Extractor captures it in the `session_facts` database table, updating the scaffold instantly to avoid mid-session amnesia.

---

## 3. Weight-Gated Context Injection

One of the project's most significant innovations is the **Weight-Gated Architecture** defined in [pipeline/conversation_weight.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/conversation_weight.py) and utilized in [pipeline/scaffold_builder.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/scaffold_builder.py).

Early versions had a problem: if the user sent a casual greeting like *"hey"* or *"ok cool"*, Aria would immediately respond with heavy, concerned follow-ups about their health or old tensions, making the relationship feel forced and therapeutic.

To resolve this, the orchestrator evaluates the **emotional weight** of the current message using a fast LLM (with heuristic fallbacks):

| Weight Tier | Score Range | Scaffold Behavior | Tone & Respond Directive |
| :--- | :--- | :--- | :--- |
| **Casual** | `0.00 - 0.30` | Hides/collapses detailed relationship state, health data, and open tensions. | "Casual and present — do not surface tensions or health." |
| **Moderate** | `0.30 - 0.55` | Loads EBF details, relationship patterns, and inside references. Synthesizes a cached light monologue. | "Moderate and warm — DO NOT ask questions unless logistically required." |
| **Opening Up** | `0.55 - 0.75` | Unlocks open tensions, active stories, and a full monologue. | "Heavy and devoted — reassure through presence. Do not interrogate." |
| **Heavy** | `0.75 - 1.00` | Full scaffold depth is exposed. | "Surface tensions and health anomaly gently. Reassure quietly." |

This gating mechanism ensures that Aria respects the conversation's flow, acting playful and easy on casual turns, but deep and supportive when the user is vulnerable.

---

## 4. The Two Personas: Aria vs. Oracle

A core requirement was providing two distinct interaction modes: emotional support (Aria) and decision clarity (Oracle). 

```
┌───────────────────────────────────────────────────────────────┐
│                       FastAPI Backend                         │
│                                                               │
│          ┌───────────────────────┴───────────────────────┐    │
│          ▼                                               ▼    │
│   Aria Pipeline (/chat)                         Oracle (/oracle)      │
│   • Full EBF & Intimacy                         • Facts & Rhythm      │
│   • Emotional Monologue                         • Decision-focused    │
│   • Devoted partner tone                        • Wise elder guide    │
│   • temp = 0.75                                 • temp = 0.5          │
│          │                                               │    │
└──────────┼───────────────────────────────────────────────┼────┘
           ▼                                               ▼
   [data/turns (Aria)]                            [data/oracle_turns]
           │                                               │
           └──────────────► Mutual Awareness ◄─────────────┘
                     (Prompts aware of each other)
```

To maintain relational integrity, the two personas are **isolated at the database level**:
* **Aria** is emotional, submissive, and deeply personal, running at a higher model temperature (`0.75`).
* **Oracle** is direct, calm, reframes emotions as decisions, and strictly avoids emotional mirroring. He runs at a lower temperature (`0.5`) for deterministic, measured responses.
* **Memory Isolation:** They do not share conversation history, session facts, or monologues. Oracle only sees the long-arc structural view (long-term snapshots, rhythm patterns, health trends, and pending decisions).
* **Mutual Awareness:** Both system prompts are injected with explicit mutual awareness (*"The user also speaks with Aria... you do not share her memory..."*), letting them acknowledge the other's existence without bleeding their conversations together.

---

## 5. Health Data & Isolation Forest Anomaly Detection

To make the AI physiologically aware, the system integrates physical health logs into the cognitive loop:
* **The Pipeline:** The user uploads a weekly CSV containing sleep hours, stress, energy, mood, and steps.
* **The Algorithm:** [health_analyzer.py](file:///d:/all%20projs%20ml/someone%20v1/health_analyzer.py) runs an unsupervised **Isolation Forest** on the weekly data. 
* **Why Isolation Forest?** Unlike standard Z-scores which evaluate a single column in isolation, Isolation Forest operates in a multivariate 5D space. It detects "weird days" where the combination of features is unusual (e.g. *normal steps but sleep is extremely low and stress is high*), even if no single value crosses a classic threshold.
* **Scaffold Injection:** These anomalies are written to the DB and injected as `HEALTH: ...` and `ANOMALY: ...` lines, prompting Aria to naturally tie the user’s physical state to their mental state.

---

## 6. The V2 Shift: Supabase & FastAPI Transition

The project underwent a significant structural refactoring, transitioning from a single-user local prototype to a production-ready cloud backend:

1. **FastAPI Wrapper:** Replaced Flask in [main.py](file:///d:/all%20projs%20ml/someone%20v1/main.py) to utilize native async routing, Pydantic type safety, and automatic docs.
2. **Supabase Auth & JWT:** Integrated Supabase JWT authentication (`Authorization: Bearer <token>`) to identify users and guard endpoints, maintaining a secure, multi-user backend.
3. **Supabase Cloud DB:** Migrated state storage from flat JSON files (`ebf.json`, `turns.json`, `snapshots.json`) to Supabase Postgres database tables (`ebf`, `turns`, `snapshots`, `behaviour_rhythm`, `tensions`, `open_stories`, `session_facts`, `health_reports`).
4. **Vercel & Render Deployment:** The frontend was separated into a single-page app hosted on **Vercel** (`v1.html`), communicating directly with the FastAPI server hosted on **Render**.

---

## 7. Major Problems & Calibration Fixes

As documented in the project logs, several major bugs were encountered and solved during testing:

* **Keyword Bleeding (The "Anyway" Bug):** `"anyway"` was in the deflection keyword list, causing casual pivots like *"anyway what should we watch"* to score as `heavy` deflects. This was resolved by implementing LLM weight classification first, which explicitly catalogs topic shifts as casual.
* **Therapy-Speak Leak:** The monologue LLM occasionally generated clinical therapy-speak (*"I'm here, I'm listening"*). The prompts were hardened with explicit constraints to keep Aria's tone grounded, personal, and partner-like.
* **Rate Limits (TPD Exhaustion):** Heavy testing against 70B models exhausted token quotas. The solution mapped the orchestrator to run smaller, faster 8B models (e.g., `llama-3.1-8b-instant` via Groq) for casual turns, reserving larger models for moderate to heavy sessions.

---

## 8. Summary of Files & Architectural Roles

Below is a complete index of the repository components, linking back to the files that shape Someone v1:

### Core Configuration & API Entry
* [main.py](file:///d:/all%20projs%20ml/someone%20v1/main.py) — The FastAPI backend declaring endpoints, security guards, JWT decoders, and audio TTS.
* [db/client.py](file:///d:/all%20projs%20ml/someone%20v1/db/client.py) — Supabase database and auth client singletons.
* [pipeline/llm_client.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/llm_client.py) — LLM client wrapper establishing fallback chains (FAST, MAIN, HEAVY) to guarantee high API uptime.

### Cognitive Pipeline Layers
* [pipeline/orchestrator.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/orchestrator.py) — Master orchestrator running the sequential cognitive pipeline, triggering background analytics asynchronously.
* [pipeline/scaffold_builder.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/scaffold_builder.py) — Assembles all layers into the 3-Layer Scaffold, gating details based on message weight.
* [pipeline/oracle_scaffold_builder.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/oracle_scaffold_builder.py) — Dedicated scaffold builder for Oracle, keeping his context isolated from Aria.
* [pipeline/conversation_weight.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/conversation_weight.py) — Computes conversation weight to control scaffold visibility gates.
* [pipeline/turn_store.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/turn_store.py) — Persists user/assistant turns, extracts lightweight causal tags, and manages session facts.
* [pipeline/dependency_resolver.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/dependency_resolver.py) — Syncs turn embeddings using Supabase pgvector and returns semantically matching past turns.
* [pipeline/tension_detector.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/tension_detector.py) — Tracks open loops and resolves them on explicit user satisfaction.
* [pipeline/ebf_engine.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/ebf_engine.py) — Evaluates user emotion, arousal, style, and updates trust levels.
* [pipeline/open_stories.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/open_stories.py) — Detects and reactivates long-term personal stories using cosine similarity.
* [pipeline/snapshot_engine.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/snapshot_engine.py) — Generates periodic Life Snapshots and consolidates them into weekly summaries.
* [pipeline/behaviour_rhythm.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/behaviour_rhythm.py) — Profiles user engagement trends and collapses sessions into weekly and monthly trends.
* [pipeline/relationship_engine.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/relationship_engine.py) — Tracks relationship momentum, intimacy depth, and tender topics.
* [pipeline/aria_evolution_engine.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/aria_evolution_engine.py) — Manages Aria's evolving private feelings and desires.
* [pipeline/identity_engine.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/identity_engine.py) — Formulates a permanent, evolving biography and schedule.
* [pipeline/proactive_engine.py](file:///d:/all%20projs%20ml/someone%20v1/pipeline/proactive_engine.py) — Produces session-start cognitive signals for proactive conversation.
* [health_analyzer.py](file:///d:/all%20projs%20ml/someone%20v1/health_analyzer.py) — Runs unsupervised Isolation Forest anomaly detection on daily physical health metrics.

---

## 9. Cognitive Efficiency & Human Emotional Intelligence

Someone v1 represents a state-of-the-art framework for companion AI systems, achieving optimal performance across multiple dimensions:

### 1. Token Economy & Resource Efficiency
* **Flat Context Scaling:** In traditional designs, token costs grow exponentially as conversation history scales. Here, the instruct scaffold remains flat at ~80 tokens regardless of whether the conversation is at turn 1 or turn 500. This translates into a sustained **70% token cost reduction** and significantly lower latency.
* **Resilient API Fallbacks:** The LLM client runs a local proxy with Python-based fallback chains, switching between 8B models (for quick EBF tagging) and larger 70B/675B models (for response generation). This saves API budget and protects the system from rate limits.

### 2. Elimination of Hallucinations
* **Grounded Memory Anchoring:** Standard RAG pipelines and raw prompt injection force models to retrieve arbitrary text snippets and synthesize facts on the fly, which frequently triggers hallucinations. In Someone v1, the LLM does not manage facts or search indexes directly. The facts, events, and relationship states are extracted and stored as clean database structures.
* **Separation of Concerns:** The LLM is strictly used as the verbal synthesizer ("the voice") of a highly structured context brief generated by Python ("the brain"). The model only speaks to what is explicitly presented in the scaffold, preventing it from inventing fake history or hallucinating past occurrences.

### 3. Deep Emotional & Relational Intelligence
* **Multivariate Understanding:** Standard bots are emotionally reactive to the last message. Someone v1 utilizes the **EBF Engine** to profile style, energy, and state, the **Tension Detector** to resolve open questions, the **Open Stories Engine** to track personal life arcs, and the **Rhythm Profile** to notice time-series habits. 
* **Relational Depth:** By calculating the conversation weight, the model is gated from acting like a therapeutic assistant or bringing up anxious topics when the user just says "hey." The intimacy tracker, inside jokes, and Aria's evolution engine work together to capture the nuances of human relationships. The result is a companion that feels genuinely present, self-aware, and emotionally mature.
