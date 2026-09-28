"""CachePlannerStage: maximize provider prompt-cache hits (lossless).

Runs first in the pipeline. It never changes token content; it identifies the
byte-stable leading prefix across calls of a session, marks the Anthropic
cache boundary, flags cache-busting changes, and reports the cache-eligible
share plus the expected discount for Anthropic vs OpenAI. See
``docs/RUNTIME_STAGES_DESIGN.md``.

On OpenAI, prompt caching is automatic (no ``cache_control`` to insert), so the
stage emits no breakpoints there and only the stability/busting signals apply.
"""

from __future__ import annotations

import hashlib
from typing import Any

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.base import OptimizationContext, PipelineStage
from tokenopt.utils.token_counter import count_message_tokens

# Provider cache economics (cost of a cached input token relative to a fresh
# one → the fraction saved). Anthropic cache reads are ~0.1x (≈90% off);
# OpenAI cached input is ~0.5x (≈50% off). Configurable per instance.
ANTHROPIC_CACHE_DISCOUNT = 0.9
OPENAI_CACHE_DISCOUNT = 0.5
# Both providers require a minimum prefix length to cache at all.
DEFAULT_MIN_PREFIX_TOKENS = 1024
ANTHROPIC_MAX_BREAKPOINTS = 4


def _hash(content: Any) -> str:
    return hashlib.sha256(str(content).encode("utf-8")).hexdigest()[:16]


class CachePlannerStage(PipelineStage):
    """Plan provider prompt caching for the current call (lossless)."""

    name = "cache_planner"

    def __init__(
        self,
        config: TokenOptConfig | None = None,
        *,
        provider: str = "anthropic",
        session_id: str | None = None,
        max_breakpoints: int = ANTHROPIC_MAX_BREAKPOINTS,
        min_prefix_tokens: int = DEFAULT_MIN_PREFIX_TOKENS,
        anthropic_discount: float = ANTHROPIC_CACHE_DISCOUNT,
        openai_discount: float = OPENAI_CACHE_DISCOUNT,
    ) -> None:
        super().__init__(config)
        self.config: TokenOptConfig = config or TokenOptConfig()
        self.provider = provider.lower()
        self.session_id = session_id
        self.max_breakpoints = max(1, max_breakpoints)
        self.min_prefix_tokens = max(0, min_prefix_tokens)
        self.anthropic_discount = anthropic_discount
        self.openai_discount = openai_discount
        # session_id -> list of (role, content_hash) known stable so far.
        self._sessions: dict[str, list[tuple[str, str]]] = {}

    def _stable_prefix_len(self, sig: list[tuple[str, str]]) -> tuple[int, bool]:
        """Return (stable prefix length, cache_busted) for this call's signature."""
        sid = self.session_id
        if sid is None:
            # No cross-call memory: conservatively treat only the leading
            # system/developer messages as stable.
            n = 0
            for role, _ in sig:
                if role in ("system", "developer"):
                    n += 1
                else:
                    break
            return n, False

        prev = self._sessions.get(sid)
        if prev is None:
            self._sessions[sid] = list(sig)
            n = 0
            for role, _ in sig:
                if role in ("system", "developer"):
                    n += 1
                else:
                    break
            return n, False

        common = 0
        for a, b in zip(sig, prev):
            if a == b:
                common += 1
            else:
                break
        busted = common < len(prev)
        self._sessions[sid] = list(sig[:common])
        return common, busted

    def process(self, ctx: OptimizationContext) -> OptimizationContext:
        messages = ctx.messages
        sig = [(str(m.get("role", "")), _hash(m.get("content", ""))) for m in messages]
        stable_len, busted = self._stable_prefix_len(sig)

        total = count_message_tokens(messages, ctx.model)
        eligible = (
            count_message_tokens(messages[:stable_len], ctx.model) if stable_len else 0
        )
        cacheable = eligible >= self.min_prefix_tokens

        breakpoints: list[int] = []
        if self.provider == "anthropic" and cacheable and stable_len:
            # One breakpoint at the end of the stable prefix (cap at max).
            breakpoints = [stable_len - 1][: self.max_breakpoints]
            for idx in breakpoints:
                ctx.messages[idx] = {**ctx.messages[idx], "cache_control": {"type": "ephemeral"}}

        saved_anthropic = eligible * self.anthropic_discount if cacheable else 0.0
        saved_openai = eligible * self.openai_discount if cacheable else 0.0

        ctx.metadata["cache_breakpoints"] = breakpoints
        ctx.metrics["cache_provider"] = self.provider
        ctx.metrics["cache_stable_prefix_messages"] = stable_len
        ctx.metrics["cache_eligible_tokens"] = eligible
        ctx.metrics["cache_eligible_pct"] = round(eligible / total * 100, 3) if total else 0.0
        ctx.metrics["cache_below_min_prefix"] = not cacheable
        ctx.metrics["cache_busting_detected"] = busted
        ctx.metrics["cache_breakpoints"] = len(breakpoints)
        ctx.metrics["cache_expected_saved_tokens_anthropic"] = round(saved_anthropic, 1)
        ctx.metrics["cache_expected_saved_tokens_openai"] = round(saved_openai, 1)
        return ctx
