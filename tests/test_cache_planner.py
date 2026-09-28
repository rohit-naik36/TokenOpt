"""Tests for CachePlannerStage (lossless prompt-cache planning)."""

from __future__ import annotations

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.base import OptimizationContext
from tokenopt.pipeline.cache_planner import CachePlannerStage

MODEL = "gpt-4o"
BIG = "word " * 400  # ~400 tokens, above the 1024-token prefix floor when doubled


def _ctx(messages: list[dict]) -> OptimizationContext:
    return OptimizationContext(
        messages=[dict(m) for m in messages],
        model=MODEL,
        config=TokenOptConfig(),
        model_explicit=True,
    )


def _call(stage: CachePlannerStage, messages: list[dict]) -> OptimizationContext:
    return stage.process(_ctx(messages))


def test_stable_prefix_converges_across_calls() -> None:
    """Leading messages identical on every call become the stable prefix."""
    stage = CachePlannerStage(session_id="s1", provider="anthropic", min_prefix_tokens=0)
    base = [
        {"role": "system", "content": "SYS " + BIG},
        {"role": "user", "content": "DEMO " + BIG},
        {"role": "user", "content": "issue text"},
    ]
    _call(stage, base)  # first call seeds
    ctx2 = _call(stage, base + [{"role": "assistant", "content": "step 1"},
                                {"role": "user", "content": "obs 1"}])
    assert ctx2.metrics["cache_stable_prefix_messages"] == 3
    assert ctx2.metrics["cache_eligible_tokens"] > 0
    assert ctx2.metrics["cache_busting_detected"] is False


def test_cache_busting_detected_when_prefix_changes() -> None:
    """A change in a previously-stable leading message is flagged as busting."""
    stage = CachePlannerStage(session_id="s2", provider="anthropic", min_prefix_tokens=0)
    _call(stage, [{"role": "system", "content": "stable system"},
                  {"role": "user", "content": "task"}])
    ctx = _call(stage, [{"role": "system", "content": "CHANGED system"},
                        {"role": "user", "content": "task"}])
    assert ctx.metrics["cache_busting_detected"] is True


def test_anthropic_inserts_breakpoint_openai_does_not() -> None:
    """Anthropic gets a cache_control breakpoint at the prefix end; OpenAI gets none."""
    msgs = [{"role": "system", "content": BIG + BIG}, {"role": "user", "content": "q"}]
    # No session id: fallback prefix is the leading system message only (index 0).
    ctx_a = CachePlannerStage(provider="anthropic", min_prefix_tokens=0).process(_ctx(msgs))
    assert ctx_a.metrics["cache_breakpoints"] == 1
    assert ctx_a.metadata["cache_breakpoints"] == [0]
    assert ctx_a.messages[0].get("cache_control") == {"type": "ephemeral"}

    ctx_o = CachePlannerStage(provider="openai", min_prefix_tokens=0).process(_ctx(msgs))
    assert ctx_o.metrics["cache_breakpoints"] == 0
    assert "cache_control" not in ctx_o.messages[0]


def test_below_min_prefix_is_not_cacheable() -> None:
    """A short prefix under the provider minimum is reported not cacheable."""
    stage = CachePlannerStage(session_id="s3", provider="anthropic", min_prefix_tokens=1024)
    msgs = [{"role": "system", "content": "short"}, {"role": "user", "content": "q"}]
    stage.process(_ctx(msgs))
    ctx = stage.process(_ctx(msgs))
    assert ctx.metrics["cache_below_min_prefix"] is True
    assert ctx.metrics["cache_expected_saved_tokens_anthropic"] == 0


def test_expected_discount_anthropic_exceeds_openai() -> None:
    """Anthropic expected saving is larger than OpenAI for the same prefix."""
    stage = CachePlannerStage(session_id="s4", provider="anthropic", min_prefix_tokens=0)
    msgs = [{"role": "system", "content": BIG + BIG}, {"role": "user", "content": "q"}]
    stage.process(_ctx(msgs))
    ctx = stage.process(_ctx(msgs))
    assert (
        ctx.metrics["cache_expected_saved_tokens_anthropic"]
        > ctx.metrics["cache_expected_saved_tokens_openai"]
        > 0
    )
