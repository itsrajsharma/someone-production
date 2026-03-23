# Someone v1 — Empathic Companion Pipeline: Walkthrough

## What Was Built

A complete **pipeline-first AI companion backend** for Aria. The model (Mistral) is just the voice — all intelligence lives in the Python pipeline.

## Files Created

```
pipeline/
  __init__.py
  turn_store.py          ← Layer 1: saves turns with causal tags
  dependency_resolver.py ← Layer 1: TF-IDF cosine similarity to find relevant past turns
  tension_detector.py    ← Layer 2: detects + resolves open loops
  ebf_engine.py          ← Layer 3: Emotional Behavioural Fingerprint, per-turn
  open_stories.py        ← Layer 4: tracks + reactivates unfinished stories
  snapshot_engine.py     ← Layer 4: Life Snapshot every 10 turns
  behaviour_rhythm.py    ← Layer 4: Behavioural Rhythm Profile across sessions
  scaffold_builder.py    ← Compresses all layers to ~60-80 token scaffold
  orchestrator.py        ← Master pipeline: runs all layers, calls Mistral

data/                    ← Auto-created on first run
  turns.json, ebf.json, snapshots.json, open_stories.json, rhythm.json

main.py                  ← Flask server (/chat, /status routes)
```

## Test Results (Dry Run — No API Call)

| Test | Result |
|------|--------|
| Turn store saves with causal tags | ✅ |
| EBF detects `frustrated, direct, energy=high` from `!!` | ✅ |
| Open story detected from "fight with my friend" | ✅ |
| Tension flagged as `open_question` from `should i...?` | ✅ |
| Scaffold assembled: CONTEXT + INTENT + OPEN LOOP | ✅ |
| All imports resolve cleanly | ✅ |

## How to Run

```powershell
cd "d:\all projs ml\someone v1"
.\someone\Scripts\python.exe main.py
```

Then open [v1.html](file:///d:/all%20projs%20ml/someone%20v1/v1.html) in your browser. The chat sends to `http://127.0.0.1:5000/chat`.

Check pipeline state at any time: `http://127.0.0.1:5000/status`

## What the Scaffold Looks Like (Example)

```
CONTEXT: USER: I had a fight with Raju | ASSISTANT: That sounds tough
LAST DECISION: That sounds real tough. What happened?
CURRENT INTENT: sharing or venting
KNOWN: has friend named Raju
OPEN LOOP: open question: should i even bother reaching out?
MEMORY: relates to 'i had a fight with my' — I had a huge fight with my friend Raju
EMOTIONAL STATE: frustrated, direct, energy=high
RESPOND: punchy, match energy, validate

USER: I am thinking about that whole situation again
```

**~80 tokens. Flat forever. Relationship of months compressed into a brief.**
