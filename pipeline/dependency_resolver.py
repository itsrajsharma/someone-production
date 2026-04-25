"""
Layer 1 — Dependency Resolver
Given the current user message, finds the 3 past turns it most causally depends on
using Sentence Transformers + pgvector (Supabase) over past turns.
Falls back to TF-IDF if pgvector fails.

All operations are scoped by user_id + persona.
"""

import os
from typing import List, Dict, Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine

from .turn_store import get_all_turns, extract_tags
from db.client import get_db

# ── Sentence Transformer (lazy load) ──────────────────────────────────────────

_model = None
_model_initialized = False
EMBEDDINGS_AVAILABLE = False

def _get_model():
    global _model, _model_initialized, EMBEDDINGS_AVAILABLE
    if not _model_initialized:
        _model_initialized = True
        try:
            from sentence_transformers import SentenceTransformer
            print("[DependencyResolver] Loading SentenceTransformer...")
            _model = SentenceTransformer("all-MiniLM-L6-v2")
            EMBEDDINGS_AVAILABLE = True
        except Exception as _e:
            _model = None
            EMBEDDINGS_AVAILABLE = False
            print(f"[DependencyResolver] SentenceTransformer unavailable — TF-IDF fallback active: {_e}")
    return _model


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tag_overlap_bonus(tags_a: dict, tags_b: dict) -> float:
    """Score bonus for shared topics or entities between two turns."""
    bonus = 0.0
    shared_topics = set(tags_a.get("topics", [])) & set(tags_b.get("topics", []))
    shared_entities = set(tags_a.get("entities", [])) & set(tags_b.get("entities", []))
    bonus += len(shared_topics) * 0.15
    bonus += len(shared_entities) * 0.20
    if tags_a.get("has_goal") and tags_b.get("has_goal"):
        bonus += 0.10
    return bonus


# ── pgvector sync ─────────────────────────────────────────────────────────────

def _sync_pgvector(all_turns: list, user_id: str, persona: str = "aria"):
    """
    Ensure all new turns are embedded in turn_embeddings.
    Only embeds turns not already present (checked by turn_id + user_id).
    """
    model = _get_model()
    if not all_turns or not EMBEDDINGS_AVAILABLE:
        return

    db = get_db()
    # Fetch already-embedded turn IDs for this user+persona
    existing = (
        db.table("turn_embeddings")
        .select("turn_id")
        .eq("user_id", user_id)
        .eq("persona", persona)
        .execute()
    )
    existing_ids = {r["turn_id"] for r in existing.data}

    to_embed = [t for t in all_turns if str(t.get("id", "")) not in existing_ids]
    if not to_embed:
        return

    # Batch embed
    texts = [t.get("content", "") for t in to_embed]
    try:
        embeddings = model.encode(texts).tolist()
    except Exception as e:
        print(f"[DependencyResolver] Embedding failed: {e}")
        return

    rows = []
    for turn, embedding in zip(to_embed, embeddings):
        rows.append({
            "user_id": user_id,
            "persona": persona,
            "turn_pk": turn.get("pk", turn.get("id", "")),  # use pk if available
            "turn_id": str(turn.get("id", "")),
            "content": turn.get("content", ""),
            "embedding": embedding,
        })

    # Insert in batches of 100
    for i in range(0, len(rows), 100):
        batch = rows[i : i + 100]
        try:
            db.table("turn_embeddings").upsert(batch, on_conflict="turn_id,user_id").execute()
        except Exception as e:
            print(f"[DependencyResolver] pgvector insert failed: {e}")


# ── pgvector cosine search ────────────────────────────────────────────────────

def _pgvector_search(
    query_embedding: list,
    user_id: str,
    persona: str,
    top_k: int,
) -> list:
    """
    Run pgvector cosine similarity search via Supabase RPC.
    Requires a Postgres function `match_turn_embeddings` (see below).
    Falls back to client-side sorting if RPC unavailable.
    """
    db = get_db()
    try:
        # Use the Supabase RPC for efficient pgvector search
        result = db.rpc(
            "match_turn_embeddings",
            {
                "query_embedding": query_embedding,
                "match_user_id": user_id,
                "match_persona": persona,
                "match_count": top_k * 2,  # fetch extra, filter later
            },
        ).execute()
        return result.data or []
    except Exception as e:
        print(f"[DependencyResolver] RPC match_turn_embeddings failed: {e} — using client-side fallback")
        # Client-side fallback: fetch all embeddings and compute cosine locally
        all_emb = (
            db.table("turn_embeddings")
            .select("turn_id, content, embedding")
            .eq("user_id", user_id)
            .eq("persona", persona)
            .execute()
        )
        if not all_emb.data:
            return []

        q = np.array(query_embedding).reshape(1, -1)
        results = []
        for row in all_emb.data:
            emb = np.array(row["embedding"]).reshape(1, -1)
            score = float(sklearn_cosine(q, emb)[0][0])
            results.append({"turn_id": row["turn_id"], "content": row["content"], "similarity": score})

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[: top_k * 2]


# ── TF-IDF fallback ───────────────────────────────────────────────────────────

def _fallback_resolve_dependencies(
    current_message: str,
    top_k: int,
    all_turns: list,
) -> list:
    if not all_turns:
        return []

    current_tags = extract_tags(current_message)
    texts = [t["content"] for t in all_turns]

    try:
        vectorizer = TfidfVectorizer(stop_words="english", min_df=1)
        all_texts = texts + [current_message]
        tfidf_matrix = vectorizer.fit_transform(all_texts)
        current_vec = tfidf_matrix[-1]
        past_vecs = tfidf_matrix[:-1]
        similarities = sklearn_cosine(current_vec, past_vecs).flatten()
    except Exception:
        similarities = np.zeros(len(texts))

    scores = []
    for i, turn in enumerate(all_turns):
        tag_bonus = _tag_overlap_bonus(current_tags, turn.get("causal_tags", {}))
        final_score = float(similarities[i]) + tag_bonus
        scores.append((final_score, i, turn))

    scores.sort(key=lambda x: x[0], reverse=True)
    top = scores[:top_k]
    return sorted([item[2] for item in top], key=lambda t: t.get("timestamp", ""))


# ── Public API ────────────────────────────────────────────────────────────────

def resolve_dependencies(
    current_message: str,
    user_id: str,
    persona: str = "aria",
    top_k: int = 3,
) -> list:
    """
    Returns list of up to `top_k` past turns most causally relevant to the current message.
    Uses pgvector (cosine similarity), falls back to TF-IDF.
    """
    all_turns = get_all_turns(user_id, persona)
    if not all_turns:
        return []

    model = _get_model()
    if not EMBEDDINGS_AVAILABLE:
        return _fallback_resolve_dependencies(current_message, top_k, all_turns)

    try:
        # 1. Sync any new turns into pgvector
        _sync_pgvector(all_turns, user_id, persona)

        # 2. Embed the query message
        query_embedding = model.encode([current_message]).tolist()[0]

        # 3. Search pgvector
        matches = _pgvector_search(query_embedding, user_id, persona, top_k)

        if not matches:
            return _fallback_resolve_dependencies(current_message, top_k, all_turns)

        # 4. Match back to full turn dicts (for causal_tags etc.)
        matched_ids = {m["turn_id"] for m in matches[:top_k]}
        selected = [t for t in all_turns if str(t.get("id", "")) in matched_ids]
        return sorted(selected, key=lambda t: t.get("timestamp", ""))

    except Exception as e:
        print(f"[DependencyResolver] pgvector search failed: {e}")
        return _fallback_resolve_dependencies(current_message, top_k, all_turns)
