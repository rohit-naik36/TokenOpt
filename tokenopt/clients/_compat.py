"""Provider-style compatibility shims for drop-in replacement."""

from __future__ import annotations

from typing import Any


class _CompatShim:
    """Forward ``create()`` calls to the outer optimized client.

    Exposes a provider-native entry point (``chat.completions`` or
    ``messages``) while routing through ``chat_completion``, so every
    call goes through the optimization pipeline. One implementation is
    shared by all providers: the drop-in surface must not drift.
    """

    def __init__(self, outer: Any):
        self._outer = outer

    def create(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        **kwargs: Any
    ) -> Any:
        return self._outer.chat_completion(messages, model, **kwargs)
