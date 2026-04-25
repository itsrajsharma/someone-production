# Someone v1 — Development History & Problem Log

## Overview

This document traces the full development journey of **Someone v1** — an AI companion chatbot. It documents every major problem we hit, the decisions we made, and why we changed things along the way.

---

## Phase 1: Initial Concept — "What if an AI actually remembered you?"

**Conversation:** [Building AI Companion Pipeline]

### The Idea
The starting point was frustration with existing AI chatbots: they either reset every session or blindly stuff the entire conversation history into context — which is expensive, slow, and doesn't actually make the AI *feel* like it knows you.

The goal was to build something different: a pipeline-first architecture where intelligence lives *outside* the LLM, and the model only ever sees a tight, compressed brief about the user.

### Architecture Decision: 4 Layers
The initial design proposed four distinct pipeline layers:

1. **Causal Trace Injection** — find past turns relevant to the current message
2. **Tension Detection** — track open loops (unanswered questions, unresolved goals)
3. **Emotional Behavioural Fingerprint (EBF)** — build a profile of how the user communicates and feels
4. **Long-Term Growth Memory** — snapshots of the user's life every N turns

This structure was approved and executed from scratch — the previous Flask backend was refactored to have the pipeline as the only brain; the server became just a thin HTTP wrapper.

---

## Phase 2: Building the Pipeline From Scratch

### Problem: Context Window Bloat
**Symptom:** Naive chatbots pass the entire conversation as messages, which blows up token costs and loses coherence over time.

**Fix:** The scaffold builder compresses all pipeline outputs into ~80 tokens that go into the model's `instructions` field (not the message history). The model only sees the brief + the current user message.

### Problem: "The AI doesn't remember what we talked about last week"
**Symptom:** The dependency resolver needed to find *causally relevant* past turns, not just the most recent ones.

**Fix:** We implemented `dependency_resolver.py` using **SentenceTransformers + ChromaDB** for semantic similarity search over past turns. A fallback to **TF-IDF cosine similarity** was added for environments where ChromaDB fails to import.

An additional scoring bonus was added to weight turns with shared topics, shared entities, or shared goal intent — making the retrieval more causally aware than pure semantic similarity.

### Problem: "How does the AI know how I'm feeling right now?"
**Symptom:** Early implementations just looked at keywords, missing the texture of how the user was communicating.

**Fix:** The **EBF Engine** was built as a heuristic-only module (zero LLM calls). It detects:
- **Arousal level** from caps ratio, exclamation marks, ellipsis
- **Communication style** from informal markers (lol, u, gonna, tbh) vs formal markers
- **Current emotional state** from a keyword dictionary
- **Unmet needs** from patterns like "nobody listens" or "don't know what to do"
- **Trust level** that accumulates slowly as the user shares personal things

This then generates a `RESPOND` directive in the scaffold — telling Aria *how* to speak, not just what to know.

### Problem: Open Questions Were Never Followed Up
**Symptom:** If a user asked "should I take the job?" and then moved on, the AI forgot about it entirely in the next turn.

**Fix:** `tension_detector.py` was built to track **open loops** — questions that haven't been answered and goals that haven't been addressed. Each tension is stored as a JSON record with a status of `open` or `resolved`. The most recent open loop is injected into every scaffold so Aria doesn't lose the thread.

Resolution detection also works: if the user says "that makes sense" or "got it", open loops get marked resolved.

---

## Phase 3: Long-Term Memory & Snapshots

### Problem: "The AI forgets everything between sessions"
**Symptom:** Since we're not using full chat history, facts shared weeks ago (name, job, family relationships) would vanish.

**Fix:** `snapshot_engine.py` was built to generate a **Life Snapshot** every ~10 turns. Each snapshot extracts:
- Facts (name, age, job, location, dislikes, likes) via regex patterns
- Dominant emotional tone across that turn batch
- Notable events (fights, meetings, decisions mentioned)
- Open stories

These snapshots accumulate in `snapshots.json`, and their facts are pulled into every scaffold via `get_accumulated_facts()`.

### Problem: "The AI doesn't know the user's patterns over time"
**Fix:** `behaviour_rhythm.py` aggregates across all snapshots to build a **Rhythm Profile**: when the user is most open (by time of day), trust growth rate, and storytelling frequency. This was designed to eventually help Aria adapt not just to the current message but to the user's historical patterns.

### Problem: "What about unfinished life stories?"
**Symptom:** A user mentions "I've been dealing with this situation at work" — and then next turn asks something completely different. A week later they're still dealing with it. The AI has no idea.

**Fix:** `open_stories.py` was built to detect these narratives from trigger patterns ("I've been going through…", "there's this situation…", "I had a fight with…"). When a new message is semantically similar to a stored story (TF-IDF cosine similarity > 0.25), the story is *reactivated* in the scaffold as a `MEMORY:` line. This makes Aria feel like she remembers the long arc.

---

## Phase 4: The Frontend & Health Integration

### Problem: "The app needs a real interface"
**Fix:** `v1.html` was built as a single-page app. It has two chat panels (Aria and Oracle), handles audio playback from the TTS base64 response, allows CSV health data uploads, and renders health charts from the returned stats.

### Problem: "Aria should know about the user's health"
**Symptom:** Health data existed but wasn't integrated into the AI's awareness.

**Fix:** `health_analyzer.py` was written to ingest weekly CSV files (sleep hours, stress level, energy, mood, steps) and run an **Isolation Forest** anomaly detector to find unusual days. The results — avg sleep, avg stress, trend, anomalies — are saved to `health_report.json`.

The `scaffold_builder.py` was then updated to read this file and inject a `HEALTH:` line into every scaffold. If a comparison to last week exists, that's injected too (`VS LAST WEEK: sleep +0.5hr, stress -0.3`).

A `/health` route was added to `main.py` to receive the CSV upload and archive the previous report with a timestamp before overwriting.

### Problem: Frontend Wasn't Triggering Health Context Automatically
**Symptom:** After uploading a CSV, the user had to manually say "read my health data" to get Aria to respond contextually.

**Fix:** The frontend was updated to automatically send a "health update synced" message to the `/chat` endpoint after a successful CSV upload — so Aria immediately acknowledges the data without the user having to prompt her.

---

## Phase 5: Oracle — The Second Persona

### Problem: "Aria is empathetic but sometimes I want someone brutally direct"
**Reasoning:** The user wanted two distinct interaction modes — one that meets you emotionally (Aria), and one that cuts through emotion and frames things as decisions (Oracle).

**Fix:** Oracle was added as a completely separate persona with:
- His own system prompt (direct, no emotional mirroring, reframes as decisions, speaks in long arcs)
- His own scaffold builder (`oracle_scaffold_builder.py`) — focused on facts, rhythm, health, pending decisions
- His own conversation store (`oracle_turns.json`)
- His own `/oracle` route in `main.py`

Oracle uses the same Mistral model but at lower temperature (0.5 vs 0.75) to produce more measured, deterministic responses.

### Problem: Aria Didn't Know Oracle Existed (and Vice Versa)
**Symptom:** Users would mention Oracle to Aria and she'd have no idea what they were talking about. Same issue the other way.

**Fix:** Both system prompts were updated with explicit mutual awareness. Aria's prompt now says: *"The user has also built a separate persona in this app called Oracle — a wise, experienced elder guide. You are aware Oracle exists as a separate persona. You do not share his memory or his conversations."* Oracle's prompt mirrors this awareness of Aria.

---

## Phase 6: Context Loss & Session Facts

### Problem: "Aria forgets what I said 5 messages ago"
**Symptom:** The scaffold was only injecting the last 3 recent turns. In a fast-moving conversation with context corrections ("no, I meant X"), the AI would still respond to the wrong interpretation.

**Fix 1:** The recent turn window in `scaffold_builder.py` was increased from 3 turns to **6 turns** to give more conversational buffer.

**Fix 2:** A real-time **Session Fact Extractor** was added to `turn_store.py` (`extract_session_facts()`). This function runs on every user message and captures facts like:
- Context corrections ("no, naah + clarification")
- Relationship declarations ("X is my girlfriend/brother/boss")
- Things built or created ("I made/built/created X")
- Plans and intentions ("I'm working on / I want to / I'm going to")
- Explicit back-references ("I told you about X")

These facts accumulate in-memory as a `SESSION KNOWN:` line in the scaffold — separate from the long-term snapshot facts. This fixed the "Aria misunderstood who someone is and kept getting it wrong" problem.

---

## Summary of Key Evolution

| Problem | Solution |
|---|---|
| LLM sees too much context | Compressed ~80-token scaffold architecture |
| No relevant past turn retrieval | ChromaDB + SentenceTransformers (TF-IDF fallback) |
| No emotional awareness | EBF Engine (heuristic-only, fast) |
| Open questions forgotten | Tension Detector with open loop tracking |
| Facts lost between sessions | Life Snapshot Engine every 10 turns |
| Long life arcs forgotten | Open Stories with reactivation |
| No historical pattern awareness | Behavioural Rhythm Profile across snapshots |
.| No health awareness | Isolation Forest + scaffold health injection |
| Health data not automatically surfaced | Auto `/chat` trigger after CSV upload |
| Wanted a second, different AI persona | Oracle added with separate scaffold and tone |
| Aria/Oracle didn't know about each other | Mutual awareness injected into both system prompts |
| Context corrections ignored mid-session | Session Fact Extractor (in-memory, real-time) |
| Context window too narrow | Recent turn window expanded from 3 → 6 turns |
