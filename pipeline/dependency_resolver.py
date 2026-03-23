"""
Layer 1 — Dependency Resolver
Given the current user message, finds the 2-3 past turns it most causally depends on
using TF-IDF cosine similarity + tag overlap bonus.
No LLM involved — pure Python signal matching.
"""

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from .turn_store import get_all_turns, extract_tags


def _tag_overlap_bonus(tags_a: dict, tags_b: dict) -> float:
    """Score bonus for shared topics or entities between two turns."""
    bonus = 0.0
    shared_topics = set(tags_a.get("topics", [])) & set(tags_b.get("topics", []))
    shared_entities = set(tags_a.get("entities", [])) & set(tags_b.get("entities", []))
    bonus += len(shared_topics) * 0.15
    bonus += len(shared_entities) * 0.20
    # Goal-to-goal bonus: if both turns reference goals, they're likely causally related
    if tags_a.get("has_goal") and tags_b.get("has_goal"):
        bonus += 0.10
    return bonus


def resolve_dependencies(current_message: str, top_k: int = 3) -> list:
    """
    Returns list of up to `top_k` past turns most causally relevant
    to the current message. Returns [] if not enough history.
    """
    all_turns = get_all_turns()
    # Need at least 1 past turn
    if not all_turns:
        return []

    current_tags = extract_tags(current_message)
    texts = [t["content"] for t in all_turns]

    # TF-IDF similarity
    try:
        vectorizer = TfidfVectorizer(stop_words="english", min_df=1)
        all_texts = texts + [current_message]
        tfidf_matrix = vectorizer.fit_transform(all_texts)
        current_vec = tfidf_matrix[-1]
        past_vecs = tfidf_matrix[:-1]
        similarities = cosine_similarity(current_vec, past_vecs).flatten()
    except Exception:
        # Fallback: all zeros if vectorizer fails (e.g. very short messages)
        similarities = np.zeros(len(texts))

    # Apply tag overlap bonus
    scores = []
    for i, turn in enumerate(all_turns):
        tag_bonus = _tag_overlap_bonus(current_tags, turn.get("causal_tags", {}))
        final_score = float(similarities[i]) + tag_bonus
        scores.append((final_score, i, turn))

    # Sort by score descending, take top_k
    scores.sort(key=lambda x: x[0], reverse=True)
    top = scores[:top_k]

    # Re-sort selected turns by original order (chronological)
    top_turns = sorted([item[2] for item in top], key=lambda t: t["timestamp"])

    return top_turns
