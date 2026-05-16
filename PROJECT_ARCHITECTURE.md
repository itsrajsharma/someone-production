# Someone v1 — Project Architecture & Pipeline Overview

**Someone v1** is a pipeline-first, stateful AI companion architecture designed to transcend the limitations of stateless LLMs. Instead of relying on raw context window limits, the system utilizes a multi-layered Cognitive Pipeline to extract, synthesize, and retrieve emotional fingerprints, daily routines, and highly specific semantic memories.

---

## 🛠 Tech Stack

### 1. Application Layer
- **Frontend:** Vanilla JS, HTML, TailwindCSS (Hosted on Vercel)
- **Backend Server:** Python, FastAPI (Hosted on Render)
- **TTS Engine:** Microsoft Edge TTS (`en-US-AvaMultilingualNeural`)

### 2. AI Intelligence Layer
- **Core Reasoning Engine:** Groq API (`llama-3.3-70b-versatile`) — Executes the final Orchestrator XML scaffold to generate organic, latency-free responses.
- **Data Extraction Engine:** Groq API (`llama-3.1-8b-instant`) — Acts as a silent observer handling background tasks (extracting facts, summarizing snapshots, and synthesizing profiles).

### 3. Memory & Database Layer
- **Vector Database:** Supabase PostgreSQL with `pgvector` extension
- **Semantic Embeddings:** Mistral API (`mistral-embed`) — Converts historical conversations into dense 1024-Dimensional vectors for cosine similarity search.

---

## 🧠 The 7-Layer Cognitive Pipeline

Unlike standard chatbots that simply push text to an LLM, *Someone v1* intercepts incoming messages and passes them through 7 distinct cognitive filters to construct a dynamic, XML-tagged "Brain Scaffold" before the LLM even sees the message.

### Layer 1: Turn Store & Semantic Tagging
Every message is instantly tagged with lightweight causal markers (e.g., entity extraction, emotional valence, and conversational intent). Instead of viewing messages as raw strings, the system understands if a user is "asking a question" versus "venting," altering downstream logic.

### Layer 2: Emotional Behavioral Fingerprint (EBF)
A continuous real-time tracker that gauges the user's emotional state. It mathematically balances whether the user needs an "Analytical," "Empathetic," or "Direct" response, passing a subconscious directive to the LLM.

### Layer 3: Tension & Micro-Narrative Detector
Detects conversational "open loops" (e.g., the user is waiting for an email, or feels mildly neglected). The system tracks these tensions across days until they are organically resolved, preventing the AI from dropping important ongoing sub-plots.

### Layer 4: Temporal Grounding & Rhythm Profiler
The system natively extracts the user's browser Timezone via JS headers, locking the backend to their physical reality. Furthermore, it extracts explicit daily routines (e.g., "goes to the office at 9 AM") predicting when the user is most open or stressed based on historical timestamp analysis.

### Layer 5: Core Identity Engine (Long-Term Psychology)
Every ~20 turns, the system aggregates the conversation into a "Life Snapshot". The Identity Engine then synthesizes a permanent, deeply empathetic psychological profile (Enduring Traits, Current Life Chapter) that persists forever, ensuring the AI deeply understands *who* they are talking to.

### Layer 6: Mistral Vector Memory Resolver
When a user speaks, the phrase is embedded into a 1024D vector. Within milliseconds, Supabase runs a mathematical cosine similarity search across months of chat logs to retrieve the exact timestamped contextual triggers (e.g., recalling a specific conversation from 20 days ago).

### Layer 7: The Orchestrator & XML Scaffold Builder
The final layer. It aggregates the outputs of Layers 1 through 6 into highly structured, hard-coded XML blocks (`<TEMPORAL_CONTEXT>`, `<PSYCHOLOGICAL_STATE>`, `<MEMORY_CONTEXT>`). The Groq LLM is then fed this scaffold alongside strict STABILITY RULES (banning therapy-speak and generic AI phrasing), forcing a deeply grounded, human-like response.
