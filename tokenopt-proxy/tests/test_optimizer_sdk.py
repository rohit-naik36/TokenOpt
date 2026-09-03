"""Standalone tests for the tokenopt_optimizer SDK.

These exercise the SDK purely as a library, independent of the FastAPI proxy,
proving it is embeddable on its own.
"""

import asyncio

import pytest
from tokenopt_optimizer import (
    CacheBackend,
    DegradedFidelityValidator,
    FidelityScore,
    Message,
    OptimizerConfig,
    PromptOptimizer,
    SemanticCompressorV2,
)

# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------

def test_message_from_dict():
    m = Message.from_mapping({"role": "user", "content": "hi there"})
    assert m.role == "user"
    assert m.content == "hi there"
    assert m.name is None


def test_message_from_object():
    class Obj:
        role = "assistant"
        content = "hello"

    m = Message.from_mapping(Obj())
    assert (m.role, m.content) == ("assistant", "hello")


# ---------------------------------------------------------------------------
# SemanticCompressorV2
# ---------------------------------------------------------------------------

def test_filler_removal():
    c = SemanticCompressorV2()
    out, tech = c.compress("Please basically explain it to us")
    assert "basically" not in out
    assert any(t.startswith("filler_removal") for t in tech)


def test_connector_replacement():
    c = SemanticCompressorV2()
    out, _ = c.compress("in order to survive")
    assert out == "to survive"


def test_unsafe_compress_is_semantic_shape():
    _ = SemanticCompressorV2().compress


def test_safe_compress_collapses_whitespace():
    c = SemanticCompressorV2()
    assert c.safe_compress("a   b\n\n\nc") == "a b\n\nc"


def test_headroom_fails_open_when_not_available(monkeypatch):
    import tokenopt_optimizer.compressor as comp_mod

    monkeypatch.setattr(comp_mod, "HEADROOM_AVAILABLE", False)
    c = SemanticCompressorV2()
    text = "a fairly long prompt to test"
    compressed, techniques, stats = c.compress_with_headroom(text)
    assert compressed == text
    assert techniques == []
    assert stats == {}


# ---------------------------------------------------------------------------
# DegradedFidelityValidator
# ---------------------------------------------------------------------------

def test_degraded_validator_fails_open():
    v = DegradedFidelityValidator()
    score = asyncio.run(v.validate("orig", "opt"))
    assert score.passed is True
    assert score.overall == 1.0
    assert v.get_stats()["engine"] == "degraded_passthrough"
    assert v.get_stats()["validations"] == 1


# ---------------------------------------------------------------------------
# PromptOptimizer
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_optimizer_uses_injected_validator():
    class TrackingValidator:
        def __init__(self):
            self.count = 0

        async def validate(self, original_prompt, optimized_prompt, **kwargs):
            self.count += 1
            return FidelityScore(
                overall=0.999,
                semantic_similarity=0.999,
                structural_similarity=1.0,
                llm_judge_score=None,
                passed=True,
                details={"engine": "tracking"},
            )

        def get_stats(self):
            return {}

    val = TrackingValidator()
    opt = PromptOptimizer(
        config=OptimizerConfig(enable_headroom=False),
        validator=val,
    )
    res = await opt.optimize([Message(role="user", content="Please basically tell us")])
    assert res["fidelity_passed"] is True
    assert val.count == 1  # validator actually invoked (not the degraded default)
    assert res["cache_hit"] is False
    assert res["original_tokens"] > 0
    assert res["optimized_tokens"] > 0


@pytest.mark.asyncio
async def test_optimizer_rolls_back_on_low_fidelity():
    class FailValidator:
        async def validate(self, original_prompt, optimized_prompt, **kwargs):
            return FidelityScore(
                overall=0.4,
                semantic_similarity=0.4,
                structural_similarity=1.0,
                llm_judge_score=None,
                passed=False,
                details={"engine": "strict"},
            )

        def get_stats(self):
            return {}

    opt = PromptOptimizer(
        config=OptimizerConfig(enable_headroom=False),
        validator=FailValidator(),
    )
    res = await opt.optimize([Message(role="user", content="Please basically explain it to us in order to help")])
    assert res["techniques"] == ["safe_compression"]
    assert res["fidelity_passed"] is False


@pytest.mark.asyncio
async def test_optimizer_accepts_dict_messages():
    opt = PromptOptimizer(config=OptimizerConfig(enable_headroom=False))
    res = await opt.optimize([{"role": "user", "content": "hello world"}])
    assert res["optimized_prompt"]
    assert res["original_tokens"] > 0


@pytest.mark.asyncio
async def test_optimizer_defaults_to_degraded_validator():
    opt = PromptOptimizer(config=OptimizerConfig(enable_headroom=False))
    res = await opt.optimize([Message(role="user", content="literally just a test")])
    # No validator supplied -> fails open -> passes with score 1.0
    assert res["fidelity_passed"] is True
    assert res["fidelity_score"] == 1.0


class DictCache(CacheBackend):
    """In-memory cache implementing the SDK CacheBackend protocol."""

    def __init__(self):
        self.data = {}

    def get(self, prefix, key):
        return self.data.get(f"{prefix}:{key}")

    def set(self, prefix, key, value, ttl=None):
        self.data[f"{prefix}:{key}"] = value


class AsyncDictCache(CacheBackend):
    """Async cache backend (mirrors the proxy's DistributedCache style)."""

    def __init__(self):
        self.data = {}

    async def get(self, prefix, key):
        return self.data.get(f"{prefix}:{key}")

    async def set(self, prefix, key, value, ttl=None):
        self.data[f"{prefix}:{key}"] = value


@pytest.mark.asyncio
async def test_optimizer_cache_hit_second_call():
    cache = DictCache()

    class CountingValidator:
        def __init__(self):
            self.count = 0

        async def validate(self, original_prompt, optimized_prompt, **kwargs):
            self.count += 1
            return FidelityScore(overall=1.0, semantic_similarity=1.0,
                                 structural_similarity=1.0, llm_judge_score=None,
                                 passed=True, details={"engine": "counting"})

        def get_stats(self):
            return {}

    val = CountingValidator()
    opt = PromptOptimizer(
        config=OptimizerConfig(enable_headroom=False),
        cache=cache,
        validator=val,
    )
    msgs = [Message(role="user", content="Please basically optimize this stable prompt")]

    first = await opt.optimize(msgs)
    assert first["cache_hit"] is False
    assert val.count == 1

    second = await opt.optimize(msgs)
    assert second["cache_hit"] is True
    assert val.count == 1  # not re-validated on cache hit


@pytest.mark.asyncio
async def test_cache_disabled_skips_read_write():
    class ExplodingCache(CacheBackend):
        def get(self, prefix, key):
            raise RuntimeError("should not be called")

        def set(self, prefix, key, value, ttl=None):
            raise RuntimeError("should not be called")

    opt = PromptOptimizer(
        config=OptimizerConfig(enable_headroom=False, cache_enabled=False),
        cache=ExplodingCache(),
    )
    res = await opt.optimize([Message(role="user", content="hello world")])
    assert res["optimized_prompt"]


@pytest.mark.asyncio
async def test_async_cache_backend_is_awaited():
    """Regression: the proxy's DistributedCache is async; the optimizer must
    await the returned coroutine instead of treating it as a plain value."""
    cache = AsyncDictCache()

    class AbsentValidator:
        async def validate(self, original_prompt, optimized_prompt, **kwargs):
            return FidelityScore(overall=1.0, semantic_similarity=1.0,
                                 structural_similarity=1.0, llm_judge_score=None,
                                 passed=True, details={"engine": "absent"})

        def get_stats(self):
            return {}

    opt = PromptOptimizer(
        config=OptimizerConfig(enable_headroom=False),
        cache=cache,
        validator=AbsentValidator(),
    )
    msgs = [Message(role="user", content="Please basically optimize this stable prompt")]

    first = await opt.optimize(msgs)
    assert first["cache_hit"] is False
    assert first["optimized_prompt"]  # real optimization result, not a coroutine

    second = await opt.optimize(msgs)
    assert second["cache_hit"] is True  # async cache worked: hit returned the stored value
