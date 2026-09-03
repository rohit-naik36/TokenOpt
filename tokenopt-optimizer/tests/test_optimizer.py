"""Tests for the SDK PromptOptimizer orchestration."""

import asyncio
import time

import pytest

from tokenopt_optimizer import (
    CacheBackend,
    FidelityScore,
    Message,
    OptimizerConfig,
    PromptOptimizer,
)


def _passing_validator(**kwargs):
    return FidelityScore(
        overall=1.0,
        semantic_similarity=1.0,
        structural_similarity=1.0,
        llm_judge_score=None,
        passed=True,
        details={"engine": "fake"},
    )


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


class CountingValidator:
    def __init__(self, score=None):
        self.count = 0
        self._score = score or _passing_validator
        self.last_kwargs = None

    async def validate(self, original_prompt, optimized_prompt, **kwargs):
        self.count += 1
        self.last_kwargs = kwargs
        return self._score()

    def get_stats(self):
        return {}


@pytest.mark.asyncio
async def test_optimizer_uses_injected_validator():
    val = CountingValidator()
    opt = PromptOptimizer(
        config=OptimizerConfig(enable_headroom=False),
        validator=val,
    )
    res = await opt.optimize([Message(role="user", content="Please basically tell us")])
    assert res["fidelity_passed"] is True
    assert val.count == 1
    assert res["cache_hit"] is False
    assert res["original_tokens"] > 0
    assert res["optimized_tokens"] > 0
    assert res["fidelity_details"]["engine"] == "fake"


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
    res = await opt.optimize(
        [Message(role="user", content="Please basically explain it to us in order to help")]
    )
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
    assert res["fidelity_passed"] is True
    assert res["fidelity_score"] == 1.0


@pytest.mark.asyncio
async def test_optimizer_uses_injected_compressor():
    class StubCompressor:
        def compress(self, text):
            return "SHORT", ["custom"]

        def safe_compress(self, text):
            return "SAFE"

    class StubValidator:
        async def validate(self, original_prompt, optimized_prompt, **kwargs):
            return _passing_validator()

        def get_stats(self):
            return {}

    opt = PromptOptimizer(
        config=OptimizerConfig(enable_headroom=False),
        validator=StubValidator(),
        compressor=StubCompressor(),
    )
    res = await opt.optimize([Message(role="user", content="a long prompt here")])
    assert res["optimized_prompt"] == "SHORT"
    assert res["techniques"] == ["custom"]


@pytest.mark.asyncio
async def test_optimizer_headroom_success_path():
    class FakeHeadroomCompressor:
        def __init__(self):
            self.calls = []

        def compress_with_headroom(self, text, **kwargs):
            self.calls.append(kwargs)
            return (
                "headroom compressed",
                ["headroom:x"],
                {
                    "tokens_before": 500,
                    "tokens_after": 200,
                },
            )

        def compress(self, text):
            return text, []

        def safe_compress(self, text):
            return text

    class FakeValidator:
        async def validate(self, original_prompt, optimized_prompt, **kwargs):
            return _passing_validator()

        def get_stats(self):
            return {}

    comp = FakeHeadroomCompressor()
    opt = PromptOptimizer(
        config=OptimizerConfig(enable_headroom=True, headroom_target_ratio=0.5),
        compressor=comp,
        validator=FakeValidator(),
    )
    res = await opt.optimize([Message(role="user", content="a fairly long prompt here")])
    assert res["optimized_prompt"] == "headroom compressed"
    assert "headroom:x" in res["techniques"]
    assert res["original_tokens"] == 500  # from headroom stats
    assert res["optimized_tokens"] == 200
    assert comp.calls[0]["target_ratio"] == 0.5
    assert comp.calls[0]["llm_model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_optimizer_headroom_falls_back_to_compress():
    class FakeHeadroomCompressor:
        def compress_with_headroom(self, text, **kwargs):
            return text, [], {}

        def compress(self, text):
            return "standard compressed", ["semantic_compression"]

        def safe_compress(self, text):
            return text

    class FakeValidator:
        async def validate(self, original_prompt, optimized_prompt, **kwargs):
            return _passing_validator()

        def get_stats(self):
            return {}

    opt = PromptOptimizer(
        config=OptimizerConfig(enable_headroom=True),
        compressor=FakeHeadroomCompressor(),
        validator=FakeValidator(),
    )
    res = await opt.optimize([Message(role="user", content="please basically help me here")])
    assert res["optimized_prompt"] == "standard compressed"
    assert res["techniques"] == ["semantic_compression"]


@pytest.mark.asyncio
async def test_optimizer_cache_hit_second_call():
    cache = DictCache()
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
    assert second["optimized_prompt"] == first["optimized_prompt"]
    assert second["fidelity_score"] == first["fidelity_score"]
    assert val.count == 1  # not re-validated on cache hit
    assert second["techniques"] == ["cache_hit"]


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
async def test_cache_read_exception_is_tolerated():
    class ExplodingGetCache(CacheBackend):
        def get(self, prefix, key):
            raise RuntimeError("cache down")

        def set(self, prefix, key, value, ttl=None):
            pass

    opt = PromptOptimizer(
        config=OptimizerConfig(enable_headroom=False),
        cache=ExplodingGetCache(),
        validator=CountingValidator(),
    )
    res = await opt.optimize([Message(role="user", content="please basically explain")])
    assert res["cache_hit"] is False
    assert res["optimized_prompt"]


@pytest.mark.asyncio
async def test_cache_write_exception_is_tolerated():
    class ExplodingSetCache(CacheBackend):
        def get(self, prefix, key):
            return None

        def set(self, prefix, key, value, ttl=None):
            raise RuntimeError("cache write down")

    opt = PromptOptimizer(
        config=OptimizerConfig(enable_headroom=False),
        cache=ExplodingSetCache(),
        validator=CountingValidator(),
    )
    res = await opt.optimize([Message(role="user", content="please basically explain")])
    assert res["optimized_prompt"]


@pytest.mark.asyncio
async def test_async_cache_backend_is_awaited():
    """Regression: async cache must be awaited, not treated as a plain value."""
    cache = AsyncDictCache()
    opt = PromptOptimizer(
        config=OptimizerConfig(enable_headroom=False),
        cache=cache,
        validator=CountingValidator(),
    )
    msgs = [Message(role="user", content="Please basically optimize this stable prompt")]

    first = await opt.optimize(msgs)
    assert first["cache_hit"] is False
    assert first["optimized_prompt"]

    second = await opt.optimize(msgs)
    assert second["cache_hit"] is True


@pytest.mark.asyncio
async def test_cache_key_is_stable_for_equivalent_prompts():
    opt = PromptOptimizer(config=OptimizerConfig(enable_headroom=False))
    k1 = opt._cache_key("hello world", "standard")
    k2 = opt._cache_key("hello world", "standard")
    k3 = opt._cache_key("hello world", "aggressive")
    assert k1 == k2
    assert k1 != k3
    assert k1.startswith("standard:")


def test_memory_cache_lru_eviction():
    from tokenopt_optimizer.optimizer import _MemoryCache

    tiny = _MemoryCache(max_size=2)
    tiny.set("p", "a", "1")
    tiny.set("p", "b", "2")
    # Without accessing either, "a" is oldest and should be evicted
    tiny.set("p", "c", "3")
    assert tiny.get("p", "a") is None
    assert tiny.get("p", "b") == "2"
    assert tiny.get("p", "c") == "3"


def test_memory_cache_lru_access_promotes():
    from tokenopt_optimizer.optimizer import _MemoryCache

    c = _MemoryCache(max_size=2)
    c.set("p", "a", "1")
    c.set("p", "b", "2")
    # Access "a" to promote it
    c.get("p", "a")
    # Now "b" is oldest, should be evicted
    c.set("p", "c", "3")
    assert c.get("p", "a") == "1"
    assert c.get("p", "b") is None
    assert c.get("p", "c") == "3"


def test_memory_cache_get_missing_returns_none():
    from tokenopt_optimizer.optimizer import _MemoryCache

    c = _MemoryCache()
    assert c.get("p", "missing") is None


def test_memory_cache_ttl_expiration():
    from tokenopt_optimizer.optimizer import _MemoryCache

    c = _MemoryCache(max_size=10)
    c.set("p", "k", "val", ttl=0)
    time.sleep(0.01)
    assert c.get("p", "k") is None


def test_memory_cache_default_ttl():
    from tokenopt_optimizer.optimizer import _MemoryCache

    c = _MemoryCache(max_size=10, default_ttl=0)
    c.set("p", "k", "val")
    time.sleep(0.01)
    assert c.get("p", "k") is None


def test_memory_cache_overwrite_preserves_order():
    from tokenopt_optimizer.optimizer import _MemoryCache

    c = _MemoryCache(max_size=2)
    c.set("p", "a", "1")
    c.set("p", "b", "2")
    # Overwrite "a" — should not cause eviction
    c.set("p", "a", "1b")
    assert c.get("p", "a") == "1b"
    assert c.get("p", "b") == "2"


def test_optimizer_estimate_tokens():
    opt = PromptOptimizer(config=OptimizerConfig(enable_headroom=False))
    assert opt._estimate_tokens("one two three four") == 5


def test_optimizer_custom_tokenizer():
    custom = OptimizerConfig(
        enable_headroom=False,
        tokenizer=lambda text: len(text),
    )
    opt = PromptOptimizer(config=custom)
    assert opt._estimate_tokens("hello") == 5
    assert opt._estimate_tokens("") == 0


def test_noop_cache_is_used_when_disabled():
    from tokenopt_optimizer.optimizer import _NoopCache

    c = _NoopCache()
    assert c.get("p", "k") is None
    c.set("p", "k", "v")
    assert c.get("p", "k") is None


@pytest.mark.asyncio
async def test_optimizer_empty_message_list():
    opt = PromptOptimizer(config=OptimizerConfig(enable_headroom=False))
    res = await opt.optimize([])
    assert res["optimized_prompt"] == ""
    assert res["original_tokens"] == 0
    assert res["cache_hit"] is False


@pytest.mark.asyncio
async def test_optimizer_multi_role_messages():
    opt = PromptOptimizer(config=OptimizerConfig(enable_headroom=False))
    res = await opt.optimize(
        [
            Message(role="system", content="You are helpful"),
            Message(role="user", content="hello"),
            Message(role="assistant", content="hi there"),
            Message(role="user", content="how are you"),
        ]
    )
    prompt = res["optimized_prompt"]
    assert "system: You are helpful" in prompt
    assert "user: hello" in prompt
    assert "assistant: hi there" in prompt
    assert "user: how are you" in prompt


@pytest.mark.asyncio
async def test_optimizer_passes_response_level_fidelity():
    val = CountingValidator()
    opt = PromptOptimizer(
        config=OptimizerConfig(enable_headroom=False),
        validator=val,
    )
    await opt.optimize(
        [Message(role="user", content="explain quantum computing")],
        baseline_response="Quantum computing uses qubits...",
        optimized_response="QC uses qubits...",
    )
    assert val.last_kwargs["baseline_response"] == "Quantum computing uses qubits..."
    assert val.last_kwargs["optimized_response"] == "QC uses qubits..."


@pytest.mark.asyncio
async def test_optimizer_max_messages_truncates():
    opt = PromptOptimizer(
        config=OptimizerConfig(enable_headroom=False, max_messages=2),
    )
    res = await opt.optimize(
        [
            Message(role="system", content="sys"),
            Message(role="user", content="first"),
            Message(role="user", content="second"),
            Message(role="user", content="third"),
        ]
    )
    prompt = res["optimized_prompt"]
    assert "sys" in prompt
    assert "first" in prompt
    assert "second" not in prompt
    assert "third" not in prompt


@pytest.mark.asyncio
async def test_optimizer_batch():
    opt = PromptOptimizer(config=OptimizerConfig(enable_headroom=False))
    batch = [
        [Message(role="user", content="first prompt please basically")],
        [Message(role="user", content="second prompt in order to test")],
    ]
    results = await opt.optimize_batch(batch)
    assert len(results) == 2
    assert "basically" not in results[0]["optimized_prompt"]
    assert "in order to" not in results[1]["optimized_prompt"]
    for r in results:
        assert r["cache_hit"] is False
        assert r["fidelity_passed"] is True


@pytest.mark.asyncio
async def test_optimizer_batch_with_responses():
    val = CountingValidator()
    opt = PromptOptimizer(
        config=OptimizerConfig(enable_headroom=False),
        validator=val,
    )
    batch = [
        [Message(role="user", content="prompt one")],
        [Message(role="user", content="prompt two")],
    ]
    results = await opt.optimize_batch(
        batch,
        baseline_responses=["resp1", "resp2"],
        optimized_responses=["opt1", "opt2"],
    )
    assert len(results) == 2
    assert val.count == 2


def test_optimizer_config_is_frozen():
    cfg = OptimizerConfig(enable_headroom=False)
    with pytest.raises(AttributeError):
        cfg.enable_headroom = True


def test_optimizer_config_custom_tokenizer():
    cfg = OptimizerConfig(tokenizer=lambda t: 42)
    assert cfg.tokenizer("anything") == 42


class _SlowValidator:
    """Validator that tracks peak in-flight calls to test the batch semaphore."""
    def __init__(self, delay: float = 0.01):
        self._delay = delay
        self._active = 0
        self._peak = 0

    async def validate(self, **kwargs):
        self._active += 1
        self._peak = max(self._peak, self._active)
        await asyncio.sleep(self._delay)
        self._active -= 1
        return FidelityScore(
            overall=1.0, semantic_similarity=1.0, structural_similarity=1.0,
            llm_judge_score=None, passed=True, details={"engine": "slow"},
        )


@pytest.mark.asyncio
async def test_batch_with_short_response_lists_no_index_error():
    """Short response lists must not raise IndexError; missing entries -> None."""
    opt = PromptOptimizer(
        config=OptimizerConfig(enable_headroom=False),
        validator=_SlowValidator(),
    )
    batch = [[Message(role="user", content="a")], [Message(role="user", content="b")]]
    # Only the first baseline response provided -> second is None, no crash.
    results = await opt.optimize_batch(batch, baseline_responses=["only-one"])
    assert len(results) == 2
    assert results[0]["fidelity_passed"] is True
    assert results[1]["fidelity_passed"] is True


@pytest.mark.asyncio
async def test_batch_respects_max_concurrency():
    """The batch semaphore must cap concurrent optimize() calls."""
    val = _SlowValidator(delay=0.02)
    opt = PromptOptimizer(config=OptimizerConfig(enable_headroom=False), validator=val)
    batch = [
        [Message(role="user", content=f"prompt {i}")] for i in range(8)
    ]
    await opt.optimize_batch(batch, max_concurrency=3)
    assert val._peak <= 3
    assert val._peak >= 1


def test_memory_cache_thread_safety():
    """Concurrent writes to the in-process cache must not corrupt it."""
    import threading

    from tokenopt_optimizer.optimizer import _MemoryCache

    cache = _MemoryCache(max_size=64)
    errors = []

    def worker(base: int):
        try:
            for i in range(200):
                cache.set("t", f"{base}-{i}", {"v": base * i})
                cache.get("t", f"{base}-{i}")
        except Exception as exc:  # pragma: no cover - failure path only
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(cache._store) <= 64
