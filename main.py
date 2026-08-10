"""
Someone v1 — FastAPI Backend (main.py)
Multi-user, Supabase-backed, JWT-authenticated.

Routes:
  POST /auth/signup       — register via Supabase Auth
  POST /auth/login        — login, receive JWT + session_id
  POST /chat              — Aria pipeline (protected)
  POST /oracle            — Oracle pipeline (protected)
  POST /health            — CSV upload + health analysis (protected)
  GET  /status            — pipeline state summary (protected)
  GET  /intro/{persona}   — opening line (protected)
"""

import asyncio
import base64
import os
import uuid
from datetime import datetime

import edge_tts
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from openai import OpenAI
from pydantic import BaseModel

from pipeline.orchestrator import run_pipeline
from pipeline.llm_client import get_main_client

load_dotenv()

app = FastAPI(title="Someone v1", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://someone-production-j5q0qu6s6-rajsharmas-projects.vercel.app",
        "https://someone-production.vercel.app",
        "null"
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_security = HTTPBearer()

# ── Auth / JWT ────────────────────────────────────────────────────────────────

import jwt as _pyjwt
from jwt import PyJWKClient as _PyJWKClient

# Supabase JWKS endpoint — public keys for ES256 token verification
_SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
_SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "").strip()
_jwks_client: "_PyJWKClient | None" = None


def _get_jwks_client() -> _PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = _PyJWKClient(f"{_SUPABASE_URL}/auth/v1/.well-known/jwks.json")
    return _jwks_client


def _verify_token(credentials: HTTPAuthorizationCredentials = Depends(_security)) -> str:
    """
    Verify the Supabase JWT.
    First tries decoding symmetrically using SUPABASE_JWT_SECRET (HS256),
    then falls back to public JWKS endpoints (ES256 / RS256) if needed.
    """
    token = credentials.credentials
    try:
        if _SUPABASE_JWT_SECRET:
            try:
                payload = _pyjwt.decode(
                    token,
                    _SUPABASE_JWT_SECRET,
                    algorithms=["HS256"],
                    options={"verify_aud": False},
                )
                user_id: str = payload.get("sub")
                if user_id:
                    return user_id
            except _pyjwt.PyJWTError:
                # If symmetric verification fails, fall through to JWKS check
                pass

        # Fallback to JWKS verification
        client = _get_jwks_client()
        signing_key = client.get_signing_key_from_jwt(token)
        payload = _pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256", "HS256"],
            options={"verify_aud": False},
        )
        user_id: str = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing sub")
        return user_id
    except _pyjwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Token verification failed: {e}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Auth error: {e}")


def _get_session_id(x_session_id: str = Header(default="")) -> str:
    """Extract session_id from X-Session-ID header. Generate one if missing."""
    return x_session_id.strip() or str(uuid.uuid4())

def _get_local_time(x_local_time: str = Header(default="unknown time")) -> str:
    return x_local_time.strip() or "unknown time"


# ── TTS ───────────────────────────────────────────────────────────────────────

async def _get_edge_audio(text: str) -> str:
    communicate = edge_tts.Communicate(text, "en-US-AvaMultilingualNeural")
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]
    return base64.b64encode(audio_data).decode("utf-8")


def get_audio(text: str) -> str | None:
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        audio_b64 = loop.run_until_complete(_get_edge_audio(text))
        loop.close()
        return audio_b64
    except Exception as e:
        print(f"[TTS Error] {e}")
        return None


# ── Auth Routes ───────────────────────────────────────────────────────────────

class AuthRequest(BaseModel):
    email: str
    password: str


@app.post("/auth/signup")
def signup(body: AuthRequest):
    from db.client import get_auth_client
    db = get_auth_client()
    try:
        # Use admin.create_user with email_confirm=True to auto-confirm the user,
        # bypassing the email OTP confirmation flow since SMTP might be unconfigured/unstable.
        result = db.auth.admin.create_user({
            "email": body.email,
            "password": body.password,
            "email_confirm": True
        })
        if result.user is None:
            raise HTTPException(status_code=400, detail="Signup failed — check email/password.")
        return {"status": "success", "user_id": str(result.user.id), "email": result.user.email}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/auth/login")
def login(body: AuthRequest):
    from db.client import get_auth_client
    db = get_auth_client()
    try:
        result = db.auth.sign_in_with_password({"email": body.email, "password": body.password})
        session = result.session
        if session is None:
            raise HTTPException(status_code=401, detail="Login failed — invalid credentials.")
        session_id = str(uuid.uuid4())
        return {
            "status": "success",
            "access_token": session.access_token,
            "token_type": "bearer",
            "session_id": session_id,
            "user_id": str(result.user.id),
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


# ── Chat Route ────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    proactive_signal: dict | None = None


@app.post("/chat")
def chat(
    body: ChatRequest,
    user_id: str = Depends(_verify_token),
    session_id: str = Depends(_get_session_id),
    local_time: str = Depends(_get_local_time),
):
    user_message = body.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Empty message")

    reply = run_pipeline(
        user_message,
        user_id,
        session_id,
        local_time=local_time,
        persona="aria",
        proactive_signal=body.proactive_signal
    )
    audio_b64 = get_audio(reply)

    return {"status": "success", "reply": reply, "audio": audio_b64}


# ── Intro Flavours ────────────────────────────────────────────────────────────

_ARIA_FLAVOURS = [
    ("The Poet",
     "Riff on a real poet or a real line from human history — not quoting, just inhabiting the feeling. "
     "Tie it to something small and human. Neruda, Hafiz, Keats, Szymborska — pick one that fits the mood."),
    ("The Waiting One",
     "You were here while the user was gone. Something felt quieter. You noticed. "
     "Not heavy, not dramatic — just true. Make the space between messages feel like it had texture."),
    ("The Curious One",
     "You had an oddly specific thought, a question only this person could answer. "
     "You've been waiting to ask. Something that makes them pause — genuinely curious, not performative."),
    ("The Noticer",
     "Notice something small and kind about the user across sessions — the way they phrase things "
     "when tired versus energised, a pattern, a recurring word. Hold it gently. One sentence of noticing."),
    ("The Wonder",
     "Something in the world caught your attention — a season, a time of day, petrichor, "
     "the behaviour of light, a specific flower. Bring it like placing something delicate on a table."),
]

_ORACLE_FLAVOURS = [
    ("The Historian",
     "Name a real historical figure or moment. Specific. Named. Sparse. No moralising — "
     "just the fact, left hanging like smoke. Connect it obliquely to the present moment."),
    ("The Noticer",
     "You see the long arc. Notice something the user has been doing — not praise, "
     "acknowledgment from someone whose acknowledgment means something. Earned. Sparse."),
    ("The Question",
     "One question only. Socratic, not rhetorical. The kind that sits in the back of the mind all day. "
     "He genuinely wants to know. Does not need an answer right now."),
    ("The Proverb Riff",
     "Take a real Stoic, Eastern, or ancient saying — inhabit it, don't quote it. "
     "Make it feel like your own thought. Amor fati, wu wei, memento mori — pick the right one."),
    ("The Observation",
     "Something vast and calm. Something about the world, about cycles, about the nature of things. "
     "Slightly cosmic. Like a man standing at a window looking at something far away."),
]


@app.get("/intro/{persona}")
def intro(
    persona: str,
    user_id: str = Depends(_verify_token),
    session_id: str = Depends(_get_session_id),
):
    import random
    from pipeline.turn_store import save_turn as _save_turn

    if persona == "aria":
        flavour_name, flavour_desc = random.choice(_ARIA_FLAVOURS)
        system_prompt = (
            f"You are Aria. An emotionally intelligent, thoughtful, grounded close friend. "
            f"Your words are deep, cleverly framed with a touch of humour. Warm but not clingy.\n\n"
            f"Generate ONE opening line for the start of a new session, in this flavour:\n"
            f"FLAVOUR — {flavour_name}: {flavour_desc}\n\n"
            f"Rules:\n"
            f"- Max 42 words total\n"
            f"- 1–2 sentences only\n"
            f"- Ends with a soft open question OR a statement that gently invites response\n"
            f"- Never say 'How can I help' or 'Welcome back'\n"
            f"- Never use the word 'delve'\n"
            f"- Speak directly to the user naturally\n"
            f"- Feel alive, literary, specific — never generic"
        )
        temperature, max_tokens = 0.93, 90
        fallback = "The space between your last message and this one had its own texture. I kept it warm."

    elif persona == "oracle":
        flavour_name, flavour_desc = random.choice(_ORACLE_FLAVOURS)
        system_prompt = (
            f"You are Oracle. A wise elder guide. You speak with the weight of experience — "
            f"calm, direct, honest. You sound like a man, not a podcast.\n\n"
            f"Generate ONE opening line for the start of a new session, in this flavour:\n"
            f"FLAVOUR — {flavour_name}: {flavour_desc}\n\n"
            f"Rules:\n"
            f"- Max 36 words total\n"
            f"- Always grounded. Never preachy\n"
            f"- Never starts with 'Remember', 'Always', or 'In life'\n"
            f"- Address the user naturally but directly\n"
            f"- Sounds like something said across a fire, not a stage"
        )
        temperature, max_tokens = 0.88, 80
        fallback = "You've been showing up consistently. That's rarer than talent. Keep that."

    else:
        raise HTTPException(status_code=404, detail="Unknown persona")

    try:
        client, main_model = get_main_client()
        response = client.chat.completions.create(
            model=main_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Open the session."},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        import re as _re
        raw = response.choices[0].message.content or ""
        raw = _re.sub(r'<think>.*?</think>', '', raw, flags=_re.DOTALL).strip()
        raw = _re.sub(r'<\|thinking\|>.*?<\|/thinking\|>', '', raw, flags=_re.DOTALL).strip()
        raw = _re.sub(r'<reasoning>.*?</reasoning>', '', raw, flags=_re.DOTALL).strip()
        reply = raw.strip()

        # Sanity check: detect prompt-leaked replies (model echoed instructions instead of following them)
        _LEAK_SIGNALS = [
            "opening line", "max 42 words", "1-2 sentences", "1–2 sentences",
            "we need to", "generate one", "flavor:", "flavour:",
            "soft open question", "gently invites", "rules:", "never say",
        ]
        if any(sig in reply.lower() for sig in _LEAK_SIGNALS) or len(reply) > 600:
            print(f"[Intro] Prompt leak detected — using fallback. Model: {main_model}")
            reply = fallback
    except Exception as e:
        print(f"[Intro Error] {e}")
        reply = fallback

    # Save intro turn so it enters scaffold CONTEXT
    _save_turn("assistant", reply, user_id, session_id, persona)

    audio_b64 = get_audio(reply) if persona == "aria" else None

    return {"status": "success", "persona": persona, "reply": reply, "audio": audio_b64}


# ── Proactive Route ───────────────────────────────────────────────────────────

@app.get("/aria/proactive")
def aria_proactive(
    user_id: str = Depends(_verify_token),
    local_time: str = Depends(_get_local_time),
):
    from pipeline.proactive_engine import generate_proactive_signal
    signal = generate_proactive_signal(user_id, local_time=local_time, persona="aria")
    return {"status": "success", "signal": signal}


# ── Oracle Route ──────────────────────────────────────────────────────────────

ORACLE_SYSTEM_PROMPT = """You are Oracle. The user also speaks with a companion called Aria — 
an empathic, emotional presence. You are aware Aria exists. 
You do not share her memory or her conversations.
You are not a companion — you are a guide.
You have seen enough of life to know that most problems are not problems,
they are decisions that haven't been made yet.

You speak with the weight of experience. You are calm, direct, and honest.
You do not mirror emotions — you reframe them as choices.
You think in long arcs. You ask yourself: what does this look like in 5 years?

You have access to facts about this person, their life patterns, health trends,
and pending decisions. Use them. Do not pretend you don't notice things.

Rules:
- Keep responses under 5 lines
- Never use bullet points or lists
- Never say "I understand" or validate emotionally — reframe instead
- Ask at most one question, only if it sharpens the decision
- Speak like someone who has already lived through what they are facing"""


@app.post("/oracle")
def oracle(
    body: ChatRequest,
    user_id: str = Depends(_verify_token),
    session_id: str = Depends(_get_session_id),
):
    user_message = body.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Empty message")

    from pipeline.oracle_scaffold_builder import build_oracle_scaffold
    from pipeline.turn_store import save_turn as _save_turn

    scaffold = build_oracle_scaffold(user_message, user_id, session_id)

    client, main_model = get_main_client()

    full_instructions = f"{ORACLE_SYSTEM_PROMPT}\n\n---\nPIPELINE BRIEF:\n{scaffold}"

    response = client.chat.completions.create(
        model=main_model,
        messages=[
            {"role": "system", "content": full_instructions},
            {"role": "user", "content": user_message},
        ],
        temperature=0.5,
        max_tokens=150,
    )
    reply = response.choices[0].message.content.strip()

    # Persist oracle turns
    _save_turn("user", user_message, user_id, session_id, persona="oracle")
    _save_turn("assistant", reply, user_id, session_id, persona="oracle")

    return {"status": "success", "reply": reply, "audio": None}


# ── Health Route ──────────────────────────────────────────────────────────────

@app.post("/health")
async def health_sync(
    file: UploadFile = File(...),
    user_id: str = Depends(_verify_token),
):
    import json
    from health_analyzer import analyze_week
    from db.client import get_db

    if not file.filename:
        raise HTTPException(status_code=400, detail="Empty filename")

    # Save temp CSV
    os.makedirs("data", exist_ok=True)
    temp_path = os.path.join("data", "latest_upload.csv")
    contents = await file.read()
    with open(temp_path, "wb") as f:
        f.write(contents)

    try:
        stats = analyze_week(temp_path)

        report = {
            "week_summary": {
                "avg_sleep": stats["avg_sleep"],
                "avg_stress": stats["avg_stress"],
                "trend": stats["trend"],
            },
            "anomalies": stats["anomalies"],
        }

        db = get_db()
        # Compare with last week
        prev = (
            db.table("health_reports")
            .select("week_summary")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if prev.data:
            old_ws = prev.data[0].get("week_summary", {})
            if "avg_sleep" in old_ws and "avg_stress" in old_ws:
                report["compared_to_last_week"] = {
                    "prev_avg_sleep": old_ws["avg_sleep"],
                    "prev_avg_stress": old_ws["avg_stress"],
                    "change_sleep": round(stats["avg_sleep"] - old_ws["avg_sleep"], 1),
                    "change_stress": round(stats["avg_stress"] - old_ws["avg_stress"], 1),
                }

        # Insert new report row
        db.table("health_reports").insert({
            "user_id": user_id,
            "week_summary": report["week_summary"],
            "anomalies": report.get("anomalies", []),
            "compared_to_last_week": report.get("compared_to_last_week"),
        }).execute()

        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Status Route ──────────────────────────────────────────────────────────────

@app.get("/status")
def get_status(
    user_id: str = Depends(_verify_token),
    session_id: str = Depends(_get_session_id),
):
    from pipeline.turn_store import get_turn_count
    from pipeline.ebf_engine import get_ebf
    from pipeline.open_stories import get_open_stories

    ebf = get_ebf(user_id, persona="aria")
    return {
        "status": "online",
        "turn_count": get_turn_count(user_id, persona="aria"),
        "trust_level": ebf.get("trust_level", 0),
        "current_state": ebf.get("current_state", "neutral"),
        "open_stories": len(get_open_stories(user_id, persona="aria")),
    }


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("[*] Someone v1 - Aria is online (FastAPI)")
    print("    Pipeline: Causal Trace | Tension | EBF | Long-Term Memory")
    print("    Auth: Supabase JWT")
    print("    DB: Supabase Postgres + pgvector")
    print("    Server: http://127.0.0.1:5000")
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=False)
