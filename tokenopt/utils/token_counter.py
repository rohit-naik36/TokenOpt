"""Token counting utilities using tiktoken."""

from __future__ import annotations

from functools import lru_cache

import tiktoken


@lru_cache(maxsize=128)
def get_encoding(model: str) -> tiktoken.Encoding:
    """Get tiktoken encoding for a model."""
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        # Fallback to cl100k_base for unknown models
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """Count tokens in a text string."""
    encoding = get_encoding(model)
    return len(encoding.encode(text))


def count_message_tokens(messages: list[dict], model: str = "gpt-4o") -> int:
    """Count tokens in a list of chat messages."""
    encoding = get_encoding(model)
    total = 0
    for msg in messages:
        # Each message has overhead
        total += 4  # message wrapper
        for key, value in msg.items():
            if isinstance(value, str):
                total += len(encoding.encode(value))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        for k, v in item.items():
                            if isinstance(v, str):
                                total += len(encoding.encode(v))
    total += 2  # conversation overhead
    return total


def truncate_to_tokens(text: str, max_tokens: int, model: str = "gpt-4o") -> str:
    """Truncate text to fit within max_tokens."""
    encoding = get_encoding(model)
    tokens = encoding.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return encoding.decode(tokens[:max_tokens])
