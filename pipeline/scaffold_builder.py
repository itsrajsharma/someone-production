"""
Scaffold Builder
Compresses all 4 pipeline layers into a ~60-80 token prompt scaffold
that the model receives before the user message.
"""

from .dependency_resolver import resolve_dependencies
from .tension_detector import get_top_open_loop
from .ebf_engine import get_ebf_summary, get_respond_directive
from .open_stories import check_reactivation
from .snapshot_engine import get_accumulated_facts
from .turn_store import get_all_turns


def _compress(text: str, max_chars: int) -> str:
    """Hard truncate to approximate token budget (1 token ≈ 4 chars)."""
    return text[:max_chars].strip()


def build_scaffold(user_message: str) -> str:
    """
    Build the full scaffold prompt for the current user message.
    Returns the scaffold string to prepend before USER: {message}.
    """

    # — CONTEXT: what's being discussed (from causally relevant turns) —
    relevant_turns = resolve_dependencies(user_message, top_k=3)
    if relevant_turns:
        # Compress the most relevant turn content as context
        context_parts = [f"{t['role'].upper()}: {t['content'][:40]}" for t in relevant_turns[-2:]]
        context = " | ".join(context_parts)
    else:
        context = "first message in session"
    context = _compress(context, 80)  # ~20 tokens

    # — LAST DECISION: most recent bot message (what was just established) —
    all_turns = get_all_turns()
    bot_turns = [t for t in all_turns if t["role"] == "assistant"]
    if bot_turns:
        last_decision = _compress(bot_turns[-1]["content"], 60)
    else:
        last_decision = "no prior response"

    # — CURRENT INTENT: what user wants right now —
    intent_map = {
        "question": "seeking an answer or validation",
        "statement": "sharing or venting",
    }
    from .turn_store import extract_tags
    current_tags = extract_tags(user_message)
    intent = intent_map.get(current_tags.get("intent", "statement"), "sharing")
    if current_tags.get("has_goal"):
        intent = "expressing a goal or desire"

    # — KNOWN FACTS from long-term memory —
    facts = get_accumulated_facts()
    facts_line = ""
    if facts:
        facts_line = "KNOWN: " + _compress(", ".join(facts[:4]), 80) + "\n"

    # — OPEN LOOP: most recent unresolved tension —
    open_loop = get_top_open_loop()
    open_loop_line = ""
    if open_loop:
        open_loop_line = f"OPEN LOOP: {_compress(open_loop, 60)}\n"

    # — OPEN STORY REACTIVATION —
    reactivated_story = check_reactivation(user_message)
    story_line = ""
    if reactivated_story:
        story_line = (
            f"MEMORY: relates to '{reactivated_story['title']}' "
            f"— {_compress(reactivated_story['summary'], 50)}\n"
        )

    # — EMOTIONAL STATE from EBF —
    emotional_state = get_ebf_summary()

    # — RESPOND directive from EBF —
    respond = get_respond_directive()

    # ── Assemble Scaffold ─────────────────────────────────────────────────────
    scaffold = (
        f"CONTEXT: {context}\n"
        f"LAST DECISION: {_compress(last_decision, 60)}\n"
        f"CURRENT INTENT: {intent}\n"
        f"{facts_line}"
        f"{open_loop_line}"
        f"{story_line}"
        f"EMOTIONAL STATE: {emotional_state}\n"
        f"RESPOND: {respond}\n"
    )

    return scaffold.strip()
