"""
Someone v1 — Flask Backend (main.py)
Serves the /chat endpoint. All intelligence is in the pipeline.
"""

import asyncio
import base64
import os

import edge_tts
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

from pipeline.orchestrator import run_pipeline

load_dotenv()

app = Flask(__name__)
CORS(app)

# ── TTS ───────────────────────────────────────────────────────────────────────

async def _get_edge_audio(text: str) -> str:
    """Convert text to speech using edge-tts. Returns base64-encoded mp3."""
    communicate = edge_tts.Communicate(text, "en-US-AvaMultilingualNeural")
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]
    return base64.b64encode(audio_data).decode("utf-8")


def get_audio(text: str) -> str | None:
    """Sync wrapper for the async TTS call."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        audio_b64 = loop.run_until_complete(_get_edge_audio(text))
        loop.close()
        return audio_b64
    except Exception as e:
        print(f"[TTS Error] {e}")
        return None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"status": "error", "message": "Empty message"}), 400

    # Run the full pipeline — returns Aria's text reply
    reply = run_pipeline(user_message)

    # Generate voice audio
    audio_b64 = get_audio(reply)

    return jsonify({
        "status": "success",
        "reply": reply,
        "audio": audio_b64,
    })


@app.route("/status", methods=["GET"])
def status():
    """Health check + quick state summary."""
    from pipeline.turn_store import get_turn_count
    from pipeline.ebf_engine import get_ebf
    from pipeline.open_stories import get_open_stories

    ebf = get_ebf()
    return jsonify({
        "status": "online",
        "turn_count": get_turn_count(),
        "trust_level": ebf.get("trust_level", 0),
        "current_state": ebf.get("current_state", "neutral"),
        "open_stories": len(get_open_stories()),
    })


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🟣 Someone v1 — Aria is online")
    print("   Pipeline: Causal Trace | Tension | EBF | Long-Term Memory")
    print("   Server:   http://127.0.0.1:5000")
    app.run(port=5000, debug=False, use_reloader=False)
