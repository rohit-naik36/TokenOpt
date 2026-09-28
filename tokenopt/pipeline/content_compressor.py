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
from collections.abc import Callable
from typing import Any

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.base import OptimizationContext, PipelineStage
from tokenopt.utils.token_counter import count_message_tokens

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Headroom import (optional — fail-open if unavailable or broken)
# ---------------------------------------------------------------------------

_headroom_compress: Callable[..., Any] | None
try:
    import headroom

    _headroom_compress = headroom.compress
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

    def _should_compress(self, role: str, prev_role: str, msg: dict[str, Any], roles: list[str],
                         model: str) -> bool:
        """Decide whether a message is eligible for content compression."""
        if role in roles:
            return True
        if "user-observation" in roles and role == "user" and prev_role == "assistant":
            return True
        return (
            role == "assistant"
            and count_message_tokens([msg], model) >= _LARGE_MESSAGE_THRESHOLD
        )

    def process(self, ctx: OptimizationContext) -> OptimizationContext:
        if not getattr(ctx.config, "content_compression_enabled", False):
            ctx.metrics["content_compressor_skipped"] = "disabled"
            return ctx

        roles = getattr(ctx.config, "content_compression_roles", None) or ["tool"]
        tokens_before = count_message_tokens(ctx.messages, ctx.model)

        compressed_messages: list[dict[str, Any]] = []
        format_changed: set[int] = set()
        messages_compressed = 0
        used_headroom = False
        prev_role = ""

        for idx, msg in enumerate(ctx.messages):
            role = str(msg.get("role", ""))
            content = msg.get("content", "")

            if not isinstance(content, str) or not content:
                compressed_messages.append(msg)
                prev_role = role
                continue

            if not self._should_compress(role, prev_role, msg, roles, ctx.model):
                compressed_messages.append(msg)
                prev_role = role
                continue

            new_content, fmt = self._compress(content, role)
            if fmt is not None and new_content != content:
                compressed_messages.append({**msg, "content": new_content})
                messages_compressed += 1
                format_changed.add(idx)
                if fmt == "headroom-tabular":
                    used_headroom = True
            else:
                compressed_messages.append(msg)
            prev_role = role

        ctx.messages = compressed_messages

        # Record which output messages had an intended format change so the
        # Validator can skip structural-syntax checks on them (headroom's
        # tabular form is not valid JSON) while keeping every other check.
        existing = ctx.metadata.get("content_format_changed") or set()
        ctx.metadata["content_format_changed"] = set(existing) | format_changed

        tokens_after = count_message_tokens(ctx.messages, ctx.model)
        ctx.metrics["content_compressor_applied"] = True
        ctx.metrics["content_compressor_messages_compressed"] = messages_compressed
        ctx.metrics["content_compressor_format_changed"] = sorted(format_changed)
        ctx.metrics["content_compressor_tokens_saved"] = max(0, tokens_before - tokens_after)
        ctx.metrics["content_compressor_backend"] = (
            "headroom" if self._use_headroom else "fallback"
        )
        ctx.metrics["content_compressor_headroom_effective"] = used_headroom

        return ctx

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compress(self, content: str, role: str = "tool") -> tuple[str, str | None]:
        """Compress *content*; return (new_content, format_tag).

        ``format_tag`` is ``"headroom-tabular"`` when headroom rewrote the
        content, ``"fallback-json"`` for the JSON sampler, or ``None`` when the
        content is unchanged. Fails open to the fallback, then to passthrough.
        """
        if self._use_headroom and _headroom_compress is not None:
            try:
                # headroom requires role="tool" to compress structured payloads;
                # present the eligible observation/tool content as role="tool".
                result = _headroom_compress([{"role": "tool", "content": content}])
                out = getattr(result, "messages", None)
                if out and isinstance(out[0].get("content"), str):
                    new = out[0]["content"]
                    if new and new != content and len(new) < len(content):
                        return new, "headroom-tabular"
            except Exception as exc:  # noqa: BLE001
                logger.debug("headroom.compress() failed, using fallback: %s", exc)

        try:
            new = _fallback_compress(content)
            if new != content:
                return new, "fallback-json"
        except Exception as exc:  # noqa: BLE001
            logger.debug("fallback compress failed, passing through: %s", exc)
        return content, None
