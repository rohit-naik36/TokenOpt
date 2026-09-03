"""Message helper utilities shared across pipeline stages."""

from __future__ import annotations


def get_user_query(messages: list[dict]) -> str:
    """Extract the last user message's text content ("" if none).

    Pipeline stages (router, RAG, few-shot) treat the last user message
    as the query. Keeping one implementation here prevents the semantics
    from drifting across stages.
    """
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
    return ""
