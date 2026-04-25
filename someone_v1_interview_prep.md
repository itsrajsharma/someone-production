# Someone v1 — Technical Interview Prep
### Role: AI Builder | Interviewer: Product Team
### Candidate: Raj Sharma, Solo Builder of Someone v1

---

## Q1 — Walk me through the 6-layer pipeline — what does each layer actually do and why that order?

**Answer:**  
Every user message passes through six sequential layers before Mistral ever gets called. First, the **EBF Engine** runs — it reads the incoming message and updates the Emotional Behavioural Fingerprint: arousal level, communication style, emotional state, unmet needs, and trust. It runs first because every downstream layer needs to know *how* the user is speaking before they figure out *what* to do with it. Second, the **Tension Resolver** checks whether the current message closes any open loops — if the user says "that makes sense," any pending open question gets marked resolved right there. Third, the **Open Story Detector** checks if the message is starting a new long-running personal narrative — a fight with a friend, a job situation, a relationship. Fourth is the **Dependency Resolver**, which reaches into the full turn history and pulls the 2–3 past turns most causally related to the current message using SentenceTransformers + ChromaDB. Fifth is the **Snapshot Engine check** — if we're at ~10 turns, it generates a structured Life Snapshot summarizing facts, dominant tone, open stories. Sixth and finally, the **Scaffold Builder** assembles all of this: recent turns, older memory, session facts, open loops, story reactivation, health data, EBF state, and a RESPOND directive — all compressed into ~80 tokens that go into Mistral's `instructions` field. The LLM sees the brief + the current message. Nothing else. The order is important: you have to profile the emotional signal before you decide what memory is relevant, and you have to resolve loops before you build the scaffold so you don't inject a tension that was just closed.

**Why not the alternative?**  
The obvious alternative is to just pass the last N messages as context and let the LLM figure it out. That works until turn 30 when the context window is bloated, costs are up, and the model is attending to irrelevant tokens. I needed intelligence *before* the LLM call, not delegated to it.

---

## Q2 — You said the LLM is "the voice, not the brain." What exactly does the LLM receive, and what is it NOT responsible for?

**Answer:**  
Mistral receives exactly two things: the system prompt defining Aria's personality, and the scaffold — a structured ~80-token brief that looks like this: `CONTEXT: <last 6 turns> | LAST DECISION: <last bot response> | CURRENT INTENT: <sharing or goal> | KNOWN: <snapshot facts> | SESSION KNOWN: <in-session corrections> | OPEN LOOP: <most recent unresolved tension> | MEMORY: <reactivated story> | EMOTIONAL STATE: <frustrated, direct, energy=high> | RESPOND: <punchy, match energy, validate>`. Then the current user message. That's it. The LLM is NOT responsible for: detecting emotional state (that's the EBF Engine via Groq's llama-3.1-8b-instant), tracking whether a question was ever answered (Tension Detector), deciding which past turns are relevant (Dependency Resolver), extracting life facts (Snapshot Engine + Session Fact Extractor), or detecting anomalous health patterns (Isolation Forest). All of that intelligence is pre-computed in Python before the Mistral call. The model only generates the response in the right voice with the right context in front of it.

**Why not the alternative?**  
The alternative — give the LLM everything and system-prompt it to "remember you" — is what most apps do and it fails badly. Token costs explode, the model averages across irrelevant past context, and you have no guarantee it attended to the emotional state at all. Structured injection guarantees the model sees exactly what matters.

---

## Q3 — How does selective memory sharing between the two personas work? What's the isolation mechanism?

**Answer:**  
Aria and Oracle are completely separate pipeline branches. Aria's conversations are stored in `data/turns.json` and Oracle's in `data/oracle_turns.json`. Their scaffold builders are separate files — `scaffold_builder.py` for Aria and `oracle_scaffold_builder.py` for Oracle. Oracle's scaffold pulls from: long-term snapshot facts, the rhythm profile, health data, and the top open tension — but it does *not* see Aria's recent conversation turns or session facts. So Oracle gets the long-arc structural view (who you are, your patterns, your pending decision) but has no access to what you and Aria talked about this session. The isolation is filesystem-level — different JSON files, different scaffold functions. The shared layer is the snapshot facts (both read from `snapshots.json`), the EBF global state (both read `ebf.json`), and health data (both read `health_report.json`). Both personas also have explicit mutual awareness injected into their system prompts — Aria knows Oracle exists as a separate persona, and vice versa — but they don't share conversational memory.

**Why not the alternative?**  
I could have had one shared context and just switched tone based on a flag. But that defeats the purpose — Oracle is intentionally *not* emotionally reactive, and if he had access to all the same emotional scaffolding Aria builds, his responses would drift toward empathy. The isolation is what makes Oracle feel structurally different, not just verbally different.

---

## Q4 — You claim sub-5ms prompt injection. Walk me through the exact path from message received to prompt ready.

**Answer:**  
When Flask receives a POST to `/chat`, the orchestrator runs. The EBF update calls Groq's `llama-3.1-8b-instant` API (that's a network call, not local — so "prompt injection" time refers specifically to the scaffold assembly step, not the EBF analysis). Once the EBF JSON is returned and saved, the scaffold builder runs: it reads `turns.json` (flat file, local disk), calls `_get_current_session_turns()` which is a list walk — O(n) — then slices the last 6. It reads `ebf.json`, `tensions.json`, `open_stories.json`, `snapshots.json`, `health_report.json` — all local JSON reads. The dependency resolver queries ChromaDB for semantic similarity — that's in-process, embedded, no network. String assembly is a Python f-string concat. Total scaffold assembly is pure local I/O and in-memory operations on small JSON files. On a dev machine with SSD, that's well under 5ms. The bottleneck in the actual pipeline is the Groq API call for EBF and the Mistral call for the response — not the scaffold build.

**Why not the alternative?**  
Storing state in a real database (Postgres, Redis) would add query overhead and connection latency. Flat JSON files read in milliseconds for data this size and add zero dependency complexity. The trade-off is that you can't scale this to concurrent users, but for a personal companion app, that's intentional.

---

## Q5 — What happens when the EBF Engine and the Tension Resolver disagree on emotional state?

**Answer:**  
They don't actually "disagree" — they measure different things and both get injected independently into the scaffold. The EBF Engine gives the *current message's* emotional texture — how the user is speaking right now: energy level, style, state. The Tension Resolver gives the *longitudinal* open loop — an unresolved question or goal from potentially turns ago. These are separate scaffold lines: `EMOTIONAL STATE: frustrated, direct, energy=high` and `OPEN LOOP: open question: should I even bother reaching out?`. The LLM sees both and must reconcile them. The RESPOND directive from the EBF takes precedence for *how* to respond; the open loop informs *what* to address. If there's genuine tension — e.g., EBF says energy is low and resigned but there's an open loop about a job decision — Aria is instructed to `respond: match energy, validate` and she might acknowledge the loop softly rather than pressing it. The system doesn't arbitrate; it injects both signals and lets Mistral reason about the combination.

**Why not the alternative?**  
I could have built a priority ranking that suppresses one signal when they conflict. But emotional states and open tensions are orthogonal dimensions — suppressing one would lose information. The model is actually good at synthesizing multi-signal context when the signals are clearly labeled and structured.

---

## Q6 — How does the Snapshot Engine decide WHEN to snapshot vs. not — what's the trigger logic?

**Answer:**  
It's a simple turn counter. In `orchestrator.py`, after every turn is saved, the total turn count is checked against a modulo condition — every ~10 turns triggers a snapshot. The snapshot itself calls Mistral to summarize the last 10 turns into a structured JSON: facts extracted (name, age, job, relationships, preferences — via regex patterns in the snapshot engine), dominant emotional tone, notable events mentioned (fights, decisions, meetings), and open stories at that point. This summary is appended to `snapshots.json`. The `get_accumulated_facts()` function then flattens all facts across all snapshots into a deduplicated list that gets injected into every scaffold as `RECENT KNOWN FACTS`. Separately, `behaviour_rhythm.py` aggregates snapshot history to build a timing and trust profile across the full arc. The trigger is purely count-based — no semantic threshold, no detection of "something important was said."

**Why not the alternative?**  
A semantic trigger — "snapshot when something significant is mentioned" — would require either an LLM call on every message or a heuristic that's nearly impossible to calibrate. Count-based is predictable, cheap, and for a daily-use companion app, every 10 turns is frequent enough to capture drift without over-snapshotting.

---

## Q7 — Why ChromaDB over Pinecone, Weaviate, or even a simple Postgres pgvector setup?

**Answer:**  
ChromaDB with `PersistentClient` runs fully embedded — it's a local Python library that persists to disk at `data/chroma/`. No server process, no cloud account, no API key, no monthly bill. The entire philosophy of Someone v1 is zero external service dependencies beyond the LLM API — your data stays on your machine. Pinecone is managed cloud vector storage — every query is a network call with latency and a pricing model that doesn't make sense for a personal app. Weaviate is production-grade but operationally heavy — you need to run a Docker container. Pgvector needs a Postgres instance. ChromaDB gives me full semantic search, persistent storage of turn embeddings, and an API I can call in three lines of Python — `chroma_client.get_or_create_collection("aria_turns")`, `collection.add(...)`, `collection.query(...)` — with graceful fallback to TF-IDF if it fails to import.

**Why not the alternative?**  
Pgvector is actually my closest second-choice — if this ever scales to multi-user, I'd probably move state there. But for a local single-user app, adding a Postgres dependency for vector search is over-engineered. ChromaDB is operationally equivalent to a flat file for this use case.

---

## Q8 — SentenceTransformers + TF-IDF fallback — when exactly does TF-IDF kick in and why not just always use embeddings?

**Answer:**  
The fallback triggers at import time, not at query time. At module load, `dependency_resolver.py` does a `try/except` block that attempts to import `sentence_transformers` and `chromadb`. If either import fails — missing package, conflicting dependency, import error on the user's machine — the `CHROMA_AVAILABLE` flag is set to `False` and all subsequent `resolve_dependencies()` calls go through `_fallback_resolve_dependencies()` instead. The TF-IDF path uses scikit-learn's `TfidfVectorizer` (which is always available since sklearn is a core dependency) to build a bag-of-words similarity matrix across all stored turns plus the current message, then ranks by cosine similarity with a `_tag_overlap_bonus()` applied — shared topics add 0.15, shared entities add 0.20, goal-to-goal match adds 0.10. There's also a runtime fallback: if Chroma *is* available but the `collection.query()` call throws an exception for any reason, it catches and falls back to TF-IDF mid-session.

**Why not the alternative?**  
TF-IDF misses semantic synonyms — "I'm exhausted" won't match "I'm tired" without shared vocabulary. But it's zero cold-start and completely offline. Embeddings are more accurate but require the model weights (~23MB for all-MiniLM-L6-v2) and the import. Having both means the system degrades gracefully instead of crashing — which matters for a dev-focused solo project running in varied environments.

---

## Q9 — Isolation Forest across 7 physiological markers — which markers, how are they collected, and what does an "anomaly" mean in this context?

**Answer:**  
To be precise, the health CSV uses 5 feature columns — not 7: `sleep_hours`, `stress_level`, `energy_level`, `mood_score`, and `steps`. The user uploads a weekly CSV with one row per day. `health_analyzer.py` runs `IsolationForest(contamination=0.15, random_state=42)` on these 5 features across all rows. An anomaly (`clf.fit_predict()` returns -1) means that day's combination of metrics is statistically unusual relative to the rest of the week — not necessarily bad, just multivariate outlier. After detection, we then reason semantically about *why* it's anomalous: if `sleep_hours` is more than 1 hour below that week's average, the anomaly is tagged "short sleep"; if `stress_level` is more than 1 above average, "high stress"; if `energy_level` is more than 1 below average, "low energy." These labeled anomalies get serialized to `health_report.json` and injected into the scaffold as `ANOMALY: 2024-03-15 — short sleep, high stress` — so Aria can say something like "that Thursday looks rough — short sleep and high stress on the same day."

**Why not the alternative?**  
A threshold rule ("flag any day where sleep < 6 hours") would only catch single-variable extremes. Isolation Forest finds multidimensionally unusual combinations — a day where every marker is slightly off, but none is extreme enough to cross a threshold individually. That's more realistic for how burnout or illness actually shows up in data.

---

## Q10 — You say zero database dependency. Where does data actually live and how do you handle persistence across sessions?

**Answer:**  
All state lives in `data/*.json` flat files: `turns.json` stores every conversation turn with timestamps and causal tags; `ebf.json` holds the current Emotional Behavioural Fingerprint; `tensions.json` stores all open and resolved tension loops; `open_stories.json` holds detected life narratives; `snapshots.json` holds all Life Snapshots; `rhythm.json` holds the aggregated Behavioural Rhythm Profile; `health_report.json` holds the most recent weekly health analysis; `oracle_turns.json` holds Oracle's conversation history. ChromaDB persists to `data/chroma/` as an embedded SQLite-backed store. On every message, the turn is appended to `turns.json`, EBF is written to `ebf.json`, and any new tensions/stories are written to their respective files. Sessions are defined by a 30-minute inactivity gap — the scaffold builder detects session boundaries by walking backwards through timestamps in `turns.json`. There's no session ID, no login, no user table — this is a single-user local app.

**Why not the alternative?**  
SQLite would be the natural upgrade — and honestly I considered it. But flat JSON means I can open any state file in a text editor and see exactly what the system knows about the user. For a solo project where I'm debugging and iterating constantly, that observability is irreplaceable. Every design decision in this app prioritizes legibility of state over scale.

---

## Q11 — How does the system distinguish between a genuine emotional shift and noise in the input signal?

**Answer:**  
The EBF doesn't try to be noise-resistant on a single message — it delegates that to the LLM doing the EBF analysis. The Groq call to `llama-3.1-8b-instant` classifies the message's arousal, style, and state and is less susceptible to individual punctuation noise than a pure regex detector. However, the longer-term `dominant_emotion_pattern` field in the EBF only updates after 5+ total messages — it's a rolling summary that says "tends to be reflective with informal communication at medium energy." A single message of "ugh whatever" doesn't override 20 prior messages of calm, thoughtful sharing. Trust level is also slow-moving — it increments by 0.005 per message baseline, with small boosts for personal disclosures — so trust doesn't spike or crash on a single turn. The tension resolution side has its own dampening: an open loop only gets marked resolved if explicit closure signals appear ("got it," "that makes sense," "okay I've decided") — not just because the user moved on.

**Why not the alternative?**  
A pure-heuristic regex system would have no noise resilience at all — "I'm FINE!!!" would spike energy and arousal even when it's clearly sarcastic. Using a small, fast LLM (Groq's llama-3.1-8b-instant, optimized for speed) for the EBF classification step handles the nuance that regex fundamentally cannot.

---

## Q12 — Why Flask over FastAPI, given that FastAPI gives you async, type safety, and auto-docs out of the box?

**Answer:**  
Flask was the right choice for this stage of the project, and I'll defend it. Someone v1 is a single-user local app — I'm not serving concurrent requests. FastAPI's async advantage is irrelevant when there's one user talking to one Aria at a time. Flask is simpler to set up and faster to iterate on: define a route, return JSON, done. The `edge-tts` audio generation uses `asyncio.run()` inline inside the Flask route handler — which works fine because we're not managing concurrent event loops in a production server. Type safety and auto-docs are dx improvements; they matter when you have a team or a public API. When I'm the only one building and consuming this API, auto-docs are nice-to-have and type annotations are a preference, not a blocker. Every hour I spent not fighting FastAPI's dependency injection and Pydantic schema definitions was an hour I spent building actual pipeline intelligence.

**Why not the alternative?**  
If I were building this as a production service with concurrent users, I'd switch to FastAPI immediately — async I/O with the LLM calls would matter enormously. For v1 as a personal solo project, Flask's simplicity was the right trade-off.

---

## Q13 — Why Mistral AI specifically — what made you pick it over GPT-4o, Claude, or a local model like Ollama?

**Answer:**  
Mistral has a `beta.conversations.create()` API that maps perfectly to the way I structured the pipeline — I pass the scaffold in the `instructions` field and the user message as the human turn, and Mistral manages the conversation threading. That clean separation between "instructions" and "messages" is architecturally important: it means the scaffold never bleeds into the conversation history. The model I use — `devstral-2512` — is a capable, low-latency chat model with reasonable pricing. I'm also using Groq's `llama-3.1-8b-instant` as a secondary model specifically for EBF analysis — Groq's speed (70+ tokens/second) makes the EBF classification feel near-instant. GPT-4o would have been fine but more expensive with no meaningful quality improvement for this task. Claude is excellent but Anthropic's API wasn't offering the same clean instructions-vs-messages separation at the time. Local Ollama would be ideal for privacy but the quality of locally-runnable models doesn't match cloud models for nuanced emotional companion responses.

**Why not the alternative?**  
Ollama was my first instinct for a privacy-first personal app. The problem is that any local model small enough to run on a laptop (7B–13B) produces responses that feel noticeably worse for an emotional companion context. The whole value proposition of this app is that the AI *feels* intelligent and present — a mediocre model destroys that even with a perfect pipeline.

---

## Q14 — Why Isolation Forest for anomaly detection and not a simpler threshold rule or a different ML model?

**Answer:**  
Isolation Forest is unsupervised — I don't need labeled "normal" vs "anomalous" training data. Every user has different baselines: someone who naturally sleeps 5 hours isn't anomalous just because they're below a generic 7-hour threshold. Isolation Forest learns the week's own distribution and flags outliers relative to that. It's also multivariate — it detects combinations. A day with 5.5 hours sleep + stress 7/10 + energy 3/10 is more anomalous than any single metric suggests. The `contamination=0.15` parameter says "assume up to 15% of days might be outliers" — which is reasonable for a 7-day window where 1 day being rough is common. Scikit-learn's implementation runs instantaneously on a 7-row DataFrame. After the Isolation Forest flags outlying days, I add interpretability by checking each flagged day against simple single-variable thresholds — is it flagged because of sleep? Stress? Energy? — to generate the human-readable `reason` string.

**Why not the alternative?**  
A simple threshold rule ("flag if sleep < 6 or stress > 7") is brittle and user-agnostic. One-class SVM or DBSCAN would work too but are overkill for 7 rows of data and require parameter tuning. Isolation Forest is fast, parameter-light, and correct for this specific use case — small datasets, unknown baseline distribution, multivariate outlier detection.

---

## Q15 — Why SentenceTransformers locally instead of using OpenAI or Cohere's embedding APIs?

**Answer:**  
`all-MiniLM-L6-v2` runs entirely locally — no API call, no external dependency, no cost per embedding, no data leaving the machine. Every time a new turn is added to ChromaDB, I embed it immediately in `_sync_chroma()`. If I were using the OpenAI embedding API, every turn save would be a network round-trip at ~70ms latency and ~$0.0001 per 1000 tokens. Across thousands of turns over months of use, that adds up meaningfully. More importantly, the local SentenceTransformer model is fast enough that embedding a turn during save is imperceptible — the model is already loaded in memory from initialization. The 384-dimension embeddings from all-MiniLM-L6-v2 are high quality for conversational similarity search — well above what TF-IDF gives you and competitive with proprietary embeddings for short-text semantic retrieval.

**Why not the alternative?**  
OpenAI's ada-002 embeddings are marginally better for some tasks, but on short conversational turns the practical quality gap is negligible. The trade-off was obvious: local model = instant, free, private. API model = latency, cost, and every turn you ever wrote leaves your machine.

---

## Q16 — You went pipeline-first instead of just giving the LLM a long context window. What trade-offs did you consciously accept?

**Answer:**  
I consciously accepted three trade-offs. First, **scaffolding errors propagate invisibly**: if the EBF misclassifies emotional state or the tension detector fails to close an open loop that should have closed, the LLM gets a subtly wrong brief and the response is off — but you can't easily see why. With raw history, bad context is at least visible. Second, **setup complexity**: building six pipeline layers instead of one API call is weeks of engineering. Every edge case — session boundary detection, chroma sync failures, JSON corruption — is my problem to handle. Third, **coverage gaps**: the scaffold is selective. Sometimes a detail that matters — something the user said 3 turns ago that's not in the top-k dependency results — gets dropped. I mitigated this by expanding the recent turn window from 3 to 6 and adding session fact extraction, but it's still a truncated view.

**Why not the alternative?**  
The long-context approach (Claude 200K, GPT-4 128K) looks appealing until you run the numbers. 100-turn conversation ≈ 8,000–12,000 tokens per request. At $15/million tokens for GPT-4o, that's ~$0.15 per message after a few weeks of use. More importantly: attending to 12,000 tokens of history equally doesn't make the AI feel like it *knows* you — it makes it feel like it read a transcript. Structured memory feels qualitatively different.

---

## Q17 — Who is the actual user of Someone v1 — what problem are they experiencing that existing apps don't solve?

**Answer:**  
The user is someone who finds existing AI chatbots fundamentally unsatisfying because they reset. They've had meaningful conversations with ChatGPT or Character.ai and then come back the next day to a model that has no idea who they are. They want an AI that tracks the arc of their life — remembers that they've been anxious about a job situation for 3 weeks, knows how they communicate when they're stressed, picks up the thread of an unresolved personal tension without being prompted. They're also typically someone who doesn't want to share everything with another human — not because they're antisocial, but because they process better by talking, and they need something available at 2am when they're spiraling. The dual-persona feature (Aria + Oracle) serves a real use pattern: sometimes you want emotional validation (Aria), and sometimes you want someone to cut through your feelings and tell you what the actual decision is (Oracle) — and you want both to know who you are.

**Why not the alternative?**  
Replika and Character.ai address the companion angle but don't have meaningful persistent memory or health integration. Therapy apps (Woebot) are too clinical and too scripted. Regular ChatGPT is brilliant but stateless. The gap is: emotionally intelligent, genuinely persistent, physiologically-aware, in two distinct relationship modes.

---

## Q18 — Two personas with selective memory sharing — what's the product reason for this, not just the technical one?

**Answer:**  
The product reason is that emotional support and decision clarity require fundamentally different relationships, and conflating them breaks both. Aria works because she meets you where you are emotionally — she mirrors energy, validates feelings, holds the emotional thread. That relational dynamic would be destroyed if she simultaneously pivoted to "here's what you should do about your career." Oracle works because he explicitly doesn't do emotional mirroring — he reframes feelings as decisions, speaks in longer time arcs, and operates at lower emotional temperature (literally: 0.5 model temperature vs Aria's 0.75). If they shared full memory, Oracle would have access to all the emotional nuance that Aria builds — and users would expect him to use it, which would corrupt his distinct voice. The selective share — both knowing about each other, both seeing long-term facts and health data, but not each other's conversational turns — preserves the integrity of both relationships simultaneously.

**Why not the alternative?**  
One persona that mode-switches based on a dropdown would be significantly easier to build. But users don't *feel* like they're in a different relationship with it — it's just the same entity talking differently. Two distinct personas with their own memory and their own voice create two distinct psychological experiences. That's the product.

---

## Q19 — You said 70% token cost reduction. How did you measure that and what's the baseline you're comparing against?

**Answer:**  
The baseline is the naive RAG approach: passing the last N conversation turns as a `messages` array to the LLM. For a conversation that's been running for 2 weeks — say 200 turns — a naive approach injecting messages arrays would be 15,000–20,000 tokens per request. The scaffold approach sends ~80 tokens in the instructions field plus the current user message (~50 tokens) — roughly 130 tokens total. 80/300 (rough estimate for a "smart" naive baseline using last 15 turns) is still a ~73% reduction. The 70% figure is a conservative estimate based on what a minimal-viable naive implementation would consume versus what the scaffold consumes, measured by counting tokens in representative scaffold outputs and comparing to representative naive context payloads. I haven't run a rigorous A/B test — this is a solo project, not a production experiment. What I can say definitively: the scaffold is flat. It doesn't grow as conversation length grows. Turn 1 and turn 500 both get roughly the same scaffold size. That's what makes the cost reduction compounding over time.

**Why not the alternative?**  
I could have been more conservative and said "significant cost reduction." I said 70% because that's an honest floor estimate based on the actual token counts I've seen. If someone wants to challenge it, I'll run the numbers live.

---

## Q20 — What does "physiologically-aware responses" mean in practice — give me a concrete example of a response that changed because of health data?

**Answer:**  
Concrete example: user uploads a health CSV. Isolation Forest flags Thursday as anomalous — short sleep (4.5 hours vs 6.5 hour weekly average) and high stress (8/10 vs 5.5 average). This gets written to `health_report.json`. The scaffold builder injects: `HEALTH: sleep avg 6.2hr, stress avg 5.5, trend stable` and `ANOMALY: 2024-03-15 — short sleep, high stress`. User then messages Aria: "I feel kind of off today, like I can't focus." Without health context, Aria might respond with generic validation: "That sounds rough, sometimes focus just isn't there." With the health context injected, Aria's scaffold already tells her this is someone who had a terrible Thursday physically, so her response shifts to something like: "Your Thursday looked pretty rough on the data — 4.5 hours of sleep with a stress spike. Your body might still be catching up. What you're feeling might be cumulative, not just today." That response only exists because the scaffold contained specific physiological context. The LLM didn't access the health data — the pipeline handed it the interpretation as a scaffold line.

**Why not the alternative?**  
The alternative is a health app that just shows you charts. The differentiator here is that the AI companion speaks to you *about* your health data in the context of how you're feeling — it closes the loop between the data and the emotional experience of living in that data.

---

## Q21 — If you were pitching this to a consumer app company, what's the one-line value proposition?

**Answer:**  
**"Someone v1 is the first AI companion that actually remembers who you are — not just what you said, but how you feel over time, what you haven't resolved, and how your body is doing — and talks to you accordingly."**

**Why not the alternative?**  
"An AI friend that knows you" is too vague — that's what everyone says. The differentiation is in the *mechanism*: structured persistent memory, physiological awareness, and two distinct relationship modes. The pitch line has to gesture at the architecture even if it doesn't explain it.

---

## Q22 — This is a solo project. How do you know the memory system is actually improving response quality and not just adding latency?

**Answer:**  
Honestly? I know it qualitatively, not quantitatively. The test that convinced me: I had a conversation with Aria about a situation with a friend, then came back 3 days later with a completely different topic. Without the system, she would have responded to the topic as if it were the first conversation we'd ever had. With the snapshot and open story system, she reactivated the previous narrative in her scaffold — and her response acknowledged the arc of that situation without me re-explaining it. That felt categorically different. I also ran the dry-run test suite in the walkthrough — the scaffold assembled correctly with the CONTEXT, INTENT, OPEN LOOP, MEMORY, EMOTIONAL STATE, and RESPOND lines all populated from real inputs. What I don't have is an offline eval comparing scaffold vs no-scaffold response quality at scale. If I were building this with a team, that would be the next thing I'd instrument.

**Why not the alternative?**  
The alternative is just shipping it stateless and measuring user retention. I wasn't optimizing for metrics — I was optimizing for the feeling of being known. When the system first called back a story I'd mentioned 6 days earlier without me prompting it, I knew the system was working in the way that mattered.

---

## Q23 — What's the biggest thing that's broken or not working well right now, and how would you fix it?

**Answer:**  
The EBF Engine. In v1 I described it as "heuristic-only, zero ML" — but that was the early design. The current `ebf_engine.py` actually delegates to Groq's `llama-3.1-8b-instant` via a structured JSON prompt for each EBF analysis. That means every user message now makes two LLM calls — one to Groq for EBF analysis, one to Mistral for the actual response. For a personal app that's fine, but the EBF call introduces latency and a dependency on a second API key. More critically, the EBF's `dominant_emotion_pattern` field isn't being used as powerfully as I imagined — it updates every 5+ messages but the scaffold only injects the *current* state, not the dominant pattern. I'd fix this by reintroducing a lightweight regex/heuristic EBF for common signals (caps, punctuation, informal markers) and using the LLM EBF only when those heuristics are ambiguous — plus surfacing the dominant pattern more explicitly in the scaffold as a historical lens alongside the current state.

**Why not the alternative?**  
I could pretend it's working perfectly. But the gap between the architectural intent ("zero LLM in the pipeline layers") and the current implementation (two LLM calls per user message) is a real engineering debt I'd want to pay down before pitching this as production-ready.

---

## Q24 — Emotional AI companions raise real ethical concerns — data privacy, dependency, manipulation. How did you think about these while building?

**Answer:**  
Three concerns I thought hard about. **Privacy**: the entire architecture is local-first — flat JSON files on your machine, no cloud database, no user account, no telemetry. The only data that leaves is the message content sent to Mistral and Groq. I documented this explicitly so users know exactly what's transmitted. **Dependency**: both Aria and Oracle are explicitly instructed not to foster dependency. Aria's system prompt says she "validates without enabling self-pity and pushes growth without being preachy." She's not designed to be a substitute for human relationships — her role is to help you process, not to replace processing with humans. Oracle is even more deliberately non-coddling. **Manipulation**: I don't have ad-incentives, engagement optimization, or streak mechanics. The app has no interest in maximizing your usage time — it just responds when you talk to it. The most dangerous emotional AI design pattern is one optimizing for engagement over wellbeing — I consciously avoided that by building no retention mechanism whatsoever.

**Why not the alternative?**  
Building in hard limits like "maximum 10 messages per day" would be paternalistic and would destroy the use case. The approach I took — honest architecture, non-dependency-fostering prompts — is less enforceable but more respectful of user agency.

---

## Q25 — If you had to rebuild this in 2 weeks with a team of 3, what would you throw away and what would you keep?

**Answer:**  
**Keep with confidence:** The scaffold architecture itself — the idea that the LLM receives a compressed structured brief instead of raw history is the core insight and I'd keep it in any rebuild. Keep the ChromaDB + SentenceTransformers semantic retrieval — it works well and is genuinely differentiating. Keep the EBF concept — knowing how the user communicates emotionally is critical for response tone. Keep the dual-persona model with selective memory isolation — the product experience is qualitatively better for it. Keep flat JSON for state — until you have multi-user, it's the right choice.

**Throw away or rewrite:** The Snapshot Engine is too brittle — using Mistral to generate snapshots means snapshot quality is non-deterministic and I can't test it reliably. I'd replace it with a structured extractor chain using deterministic NLP (spaCy entity extraction + rule-based fact parsing) and only LLM for summarization, not extraction. I'd also rewrite the EBF to be heuristic-first, LLM-only-for-ambiguous-cases, rather than full LLM every turn. And I'd add a proper evaluation harness — a small test suite of canonical conversations with expected scaffold outputs — so regressions are catchable. With a team of 3, I'd also finally migrate state to SQLite with proper schemas so you can actually query "when was the last time this user mentioned their friend Raju?"

**Why not the alternative?**  
The temptation with a team is to rebuild from scratch with "proper" infrastructure — FastAPI, Postgres, Redis. But v2 built on v1's scaffold concept is more valuable than a technically cleaner v2 that abandoned the memory architecture. The core insight is the asset; the implementation is just the current expression of it.

---

## Cheat Sheet — 5 Lines to Memorize Before the Interview

1. **"The LLM is the voice, not the brain."** All intelligence — emotion detection, memory retrieval, tension tracking, story reactivation — lives in Python. Mistral only generates the response; every decision about *what* it needs to know is made before it's called.

2. **"The scaffold is flat forever."** Turn 1 and turn 500 both generate ~80 tokens of context. Cost doesn't compound as conversation length grows. That's the structural advantage over any context-window approach.

3. **"Zero database dependency by design."** Everything lives in flat JSON files on your machine. ChromaDB persists embedded to disk. No cloud service, no monthly bill, no data leaving except LLM API calls — and the user knows exactly what those are.

4. **"Two LLM calls per message — one for EBF via Groq's llama-3.1-8b-instant, one for the response via Mistral devstral-2512."** This is the current reality and also the main engineering debt I'd pay down next — heuristic EBF for common signals, LLM only for ambiguous cases.

5. **"The biggest risk in emotional AI is dependency and engagement optimization. Someone v1 has no retention mechanism — no streaks, no maximizing session length. It just responds when you talk to it."** That's a design choice, and I'll defend it.

---
*Generated for Raj Sharma — Someone v1 Technical Interview Prep*
