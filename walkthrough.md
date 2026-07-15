# Someone v1 — Empathic Companion Pipeline: Walkthrough

## What Was Built

A complete **pipeline-first AI companion backend** for Aria. The model (Mistral) is just the voice — all intelligence lives in the Python pipeline.

### Supabase Auth & JWT Fixes
1. **Bypassed Email OTP for Signup:** Modified the `/auth/signup` endpoint in [main.py](file:///d:/all%20projs%20ml/someone%20v1/main.py) to use `db.auth.admin.create_user({"email": body.email, "password": body.password, "email_confirm": True})`. This creates new users as pre-confirmed, allowing them to sign in instantly without relying on unconfigured or failing SMTP OTP emails.
2. **CORS Origin Null Support:** Added `"null"` to the allowed origins list in the FastAPI CORS middleware. This enables running the frontend locally by opening [v1.html](file:///d:/all%20projs%20ml/someone%20v1/v1.html) directly via the browser's `file://` protocol without experiencing CORS blocks.
3. **Robust Token Decoding:** Updated symmetric `HS256` token verification to use the `SUPABASE_JWT_SECRET` key, with a clean fallback to asymmetric public JWKS key decoding.

---

## Files Created / Modified

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

main.py                  ← FastAPI server (/chat, /status, /auth, /health routes) [MODIFIED]
```

---

## Test Results

| Test | Result |
|------|--------|
| Supabase Auth Endpoint (Signup + Auto-confirm) | ✅ (Pre-confirmed user created successfully) |
| Supabase Auth Endpoint (Login with Password) | ✅ (Access token returned successfully) |
| CORS Verification (`null` Origin for local `file://`) | ✅ (Successfully processed local requests) |
| JWT Verification (`/status` with Bearer Token) | ✅ (Resolved sub claim user_id) |
| Turn store saves with causal tags | ✅ |
| EBF detects `frustrated, direct, energy=high` | ✅ |
| Open story detected from "fight with my friend" | ✅ |
| Tension flagged as `open_question` | ✅ |
| Scaffold assembled: CONTEXT + INTENT + OPEN LOOP | ✅ |
| All imports resolve cleanly | ✅ |

---

## How to Run

1. **Start the FastAPI Backend:**
```powershell
cd "d:\all projs ml\someone v1"
python main.py
```
*The server will boot on `http://127.0.0.1:5000` with the updated CORS and OTP bypass code.*

2. **Open the Frontend:**
Open [v1.html](file:///d:/all%20projs%20ml/someone%20v1/v1.html) in your browser. The login/signup forms will direct their auth and status calls to the backend without OTP/CORS friction.

Check pipeline status at any time: `http://127.0.0.1:5000/status`

---

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
