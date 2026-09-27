"""Content-type compression stage for the TokenOpt optimizer SDK.

Routes tool result messages (role="tool") and large assistant messages through
headroom's compress() function when available, with a pure-Python JSON array
sampler as fallback.

Fail-open contract: any exception leaves the message list unchanged.

Usage
-----
.. code-block:: python

    from tokenopt_optimizer.content_compressor import ContentCompressor, CompressorConfig
    from tokenopt_optimizer import Message

    cc = ContentCompressor()
    result = cc.compress_messages([
        Message(role="tool", content='[{"id": 1}, ...]'),
    ])
    print(result.messages_compressed, result.tokens_saved)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Headroom integration (optional)
# ---------------------------------------------------------------------------

_headroom_compress: Any = None

try:
    from headroom import compress as _headroom_compress  # type: ignore[import]
except Exception:
    _headroom_compress = None


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CompressorConfig:
    """Configuration for the ContentCompressor stage."""

    content_compression_enabled: bool = False
    """Master switch — off by default so existing behaviour is unchanged."""

    large_message_token_threshold: int = 500
    """Assistant messages with fewer estimated tokens than this are skipped."""

    array_head_fraction: float = 0.30
    """Fraction of leading items kept when sampling a JSON array."""

    array_tail_fraction: float = 0.15
    """Fraction of trailing items kept when sampling a JSON array."""

    array_min_length: int = 10
    """Arrays shorter than this are never sampled."""


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class CompressionResult:
    """Outcome of a compress_messages() call."""

    messages: list[dict[str, Any]]
    messages_compressed: int = 0
    tokens_saved: int = 0
    backend: str = "none"


# ---------------------------------------------------------------------------
# Pure-Python fallback helpers
# ---------------------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    """Rough token estimate (word-count heuristic, no external deps)."""
    return max(1, int(len(text.split()) / 0.75))


def _sample_json_array(items: list[Any], cfg: CompressorConfig) -> list[Any]:
    """Keep head + tail fractions, deduplicated by serialised form."""
    n = len(items)
    if n <= cfg.array_min_length:
        return items

    head_count = max(1, int(n * cfg.array_head_fraction))
    tail_count = max(1, int(n * cfg.array_tail_fraction))
    tail_start = max(head_count, n - tail_count)

    seen: set[str] = set()
    result: list[Any] = []
    for item in items[:head_count] + items[tail_start:]:
        key = json.dumps(item, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _fallback_compress(content: str, cfg: CompressorConfig) -> str:
    """Compress a JSON array with the pure-Python sampler; pass everything else through."""
    stripped = content.strip()
    if not (stripped.startswith("[") and stripped.endswith("]")):
        return content
    try:
        items = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return content
    if not isinstance(items, list):
        return content

    sampled = _sample_json_array(items, cfg)
    if len(sampled) == len(items):
        return content
    return json.dumps(sampled, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Main compressor class
# ---------------------------------------------------------------------------

class ContentCompressor:
    """Compress tool-result and large assistant messages, fail-open.

    Args:
        config: Optional :class:`CompressorConfig`; defaults to ``CompressorConfig()``.
    """

    def __init__(self, config: CompressorConfig | None = None) -> None:
        self.config = config or CompressorConfig()
        self._use_headroom = _headroom_compress is not None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compress_messages(
        self, messages: list[dict[str, Any]]
    ) -> CompressionResult:
        """Compress eligible messages in *messages* and return a :class:`CompressionResult`.

        The stage is a no-op when ``config.content_compression_enabled`` is
        ``False``, returning the original list unchanged.
        """
        if not self.config.content_compression_enabled:
            return CompressionResult(messages=list(messages), backend="disabled")

        backend = "headroom" if self._use_headroom else "fallback"
        result_messages: list[dict[str, Any]] = []
        messages_compressed = 0
        tokens_before_total = sum(_estimate_tokens(m.get("content", "")) for m in messages)

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if not isinstance(content, str) or not content:
                result_messages.append(msg)
                continue

            if not self._should_compress(role, content):
                result_messages.append(msg)
                continue

            new_content = self._compress(content)
            if new_content != content:
                result_messages.append({**msg, "content": new_content})
                messages_compressed += 1
            else:
                result_messages.append(msg)

        tokens_after_total = sum(_estimate_tokens(m.get("content", "")) for m in result_messages)
        tokens_saved = max(0, tokens_before_total - tokens_after_total)

        return CompressionResult(
            messages=result_messages,
            messages_compressed=messages_compressed,
            tokens_saved=tokens_saved,
            backend=backend,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _should_compress(self, role: str, content: str) -> bool:
        if role == "tool":
            return True
        if role == "assistant":
            return _estimate_tokens(content) >= self.config.large_message_token_threshold
        return False

    def _compress(self, content: str) -> str:
        """Try headroom first, fall back to the pure-Python sampler."""
        if self._use_headroom:
            try:
                result = _headroom_compress(content)
                return result if isinstance(result, str) else content
            except Exception as exc:
                logger.debug("headroom.compress() failed, using fallback: %s", exc)

        try:
            return _fallback_compress(content, self.config)
        except Exception as exc:
            logger.debug("fallback compress failed, passing through: %s", exc)
            return content
