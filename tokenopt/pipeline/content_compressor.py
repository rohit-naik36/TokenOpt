"""Content Compressor pipeline stage for TokenOpt.

This stage routes tool result messages (role="tool") and large assistant
messages through headroom's compress() function when available, or falls
back to a pure-Python JSON array sampler.

Placement: between AnalyzerStage and TransformerStage.
Behaviour: fail-open — any error leaves messages unchanged.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.base import OptimizationContext, PipelineStage
from tokenopt.utils.token_counter import count_message_tokens

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Headroom import (optional — fail-open if unavailable or broken)
# ---------------------------------------------------------------------------

try:
    from headroom import compress as _headroom_compress

    _HEADROOM_AVAILABLE = True
except Exception:  # noqa: BLE001
    _headroom_compress = None
    _HEADROOM_AVAILABLE = False


# ---------------------------------------------------------------------------
# Pure-Python fallback: JSON array sampler
# ---------------------------------------------------------------------------

_LARGE_MESSAGE_THRESHOLD = 500  # tokens; assistant messages below this are skipped


def _sample_json_array(items: list[Any]) -> list[Any]:
    """Keep first 30 % + last 15 % of array items, deduplicated.

    Deduplification works on JSON-serialised rows so that dict/list items
    compare correctly.
    """
    n = len(items)
    if n <= 10:
        return items

    head_count = max(1, int(n * 0.30))
    tail_count = max(1, int(n * 0.15))

    head = items[:head_count]
    tail = items[max(head_count, n - tail_count):]

    # Deduplicate while preserving order; use serialised form as key.
    seen: set[str] = set()
    result: list[Any] = []
    for item in head + tail:
        key = json.dumps(item, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            result.append(item)

    return result


def _fallback_compress(content: str) -> str:
    """Pure-Python fallback: sample JSON arrays, pass everything else through."""
    stripped = content.strip()
    if not (stripped.startswith("[") and stripped.endswith("]")):
        return content
    try:
        items = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return content
    if not isinstance(items, list):
        return content

    sampled = _sample_json_array(items)
    if len(sampled) == len(items):
        return content  # No reduction achieved
    return json.dumps(sampled, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------

class ContentCompressorStage(PipelineStage):
    """Compress tool-result and large assistant messages before transformation.

    Uses headroom.compress() when available; falls back to the pure-Python
    JSON array sampler otherwise. Always fail-open: any exception leaves the
    message list unchanged.
    """

    name = "content_compressor"

    def __init__(self, config: TokenOptConfig | None = None) -> None:
        super().__init__(config)
        self._use_headroom = _HEADROOM_AVAILABLE

    # ------------------------------------------------------------------
    # PipelineStage interface
    # ------------------------------------------------------------------

    def process(self, ctx: OptimizationContext) -> OptimizationContext:
        if not getattr(ctx.config, "content_compression_enabled", False):
            ctx.metrics["content_compressor_skipped"] = "disabled"
            return ctx

        tokens_before = count_message_tokens(ctx.messages, ctx.model)

        compressed_messages: list[dict[str, Any]] = []
        messages_compressed = 0

        for msg in ctx.messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if not isinstance(content, str) or not content:
                compressed_messages.append(msg)
                continue

            should_compress = role == "tool" or (
                role == "assistant"
                and count_message_tokens([msg], ctx.model) >= _LARGE_MESSAGE_THRESHOLD
            )

            if not should_compress:
                compressed_messages.append(msg)
                continue

            new_content = self._compress(content)
            if new_content != content:
                compressed_messages.append({**msg, "content": new_content})
                messages_compressed += 1
            else:
                compressed_messages.append(msg)

        ctx.messages = compressed_messages

        tokens_after = count_message_tokens(ctx.messages, ctx.model)
        tokens_saved = max(0, tokens_before - tokens_after)

        ctx.metrics["content_compressor_applied"] = True
        ctx.metrics["content_compressor_messages_compressed"] = messages_compressed
        ctx.metrics["content_compressor_tokens_saved"] = tokens_saved
        ctx.metrics["content_compressor_backend"] = (
            "headroom" if self._use_headroom else "fallback"
        )

        return ctx

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compress(self, content: str) -> str:
        """Compress *content*, falling back gracefully on any error."""
        if self._use_headroom:
            try:
                result = _headroom_compress(content)
                return result if isinstance(result, str) else content
            except Exception as exc:
                logger.debug("headroom.compress() failed, using fallback: %s", exc)

        # Pure-Python fallback
        try:
            return _fallback_compress(content)
        except Exception as exc:
            logger.debug("fallback compress failed, passing through: %s", exc)
            return content
