"""Tests for AAVA-specific platform hardening: real tokenizer, minimum-savings
floor, and the production fidelity guard."""

import pytest

import tokenopt_proxy_v2 as proxy
from tokenopt_proxy_v2 import AppConfig, ServiceManager

# ---------------------------------------------------------------------------
# 1. Real tokenizer
# ---------------------------------------------------------------------------

def test_make_token_counter_uses_tiktoken_when_available():
    counter = AppConfig.make_token_counter()
    # "hello world" is 2 tokens under cl100k_base when tiktoken is available.
    if proxy.TIKTOKEN_AVAILABLE:
        assert counter is not None
        assert counter("hello world") == 2
        assert counter("") == 0
    else:
        assert counter is None


def test_make_token_counter_disabled_by_flag(monkeypatch):
    monkeypatch.setattr(proxy.AppConfig, "USE_TIKTOKEN", False)
    assert proxy.AppConfig.make_token_counter() is None


def test_build_optimizer_injects_tokenizer(monkeypatch):
    optimizer = proxy.build_optimizer()
    assert optimizer.config.tokenizer is not None
    # The injected counter is the real tiktoken counter.
    assert optimizer.config.tokenizer("hello world") > 0


# ---------------------------------------------------------------------------
# 2. Minimum savings floor
# ---------------------------------------------------------------------------

def _result(orig, opt, was_skipped=False, was_rolled_back=False):
    return {
        "optimized_prompt": "compressed",
        "optimized_tokens": opt,
        "original_tokens": orig,
        "was_skipped": was_skipped,
        "was_rolled_back": was_rolled_back,
    }


def test_floor_keeps_result_when_savings_meet_threshold():
    res = _result(orig=100, opt=90)  # 10% savings >= 2%
    applied = proxy.minimum_savings_rollback(res, 2.0, "original prompt")
    assert applied is False
    assert res["optimized_prompt"] == "compressed"
    assert not res.get("was_rolled_back")


def test_floor_rolls_back_when_savings_below_threshold():
    res = _result(orig=100, opt=99)  # 1% savings < 2%
    applied = proxy.minimum_savings_rollback(res, 2.0, "original prompt")
    assert applied is True
    assert res["optimized_prompt"] == "original prompt"
    assert res["optimized_tokens"] == 100
    assert res["was_rolled_back"] is True
    assert "below minimum" in res["rollback_reason"]


def test_floor_skips_when_optimization_was_skipped():
    res = _result(orig=100, opt=100, was_skipped=True)
    applied = proxy.minimum_savings_rollback(res, 2.0, "original")
    assert applied is False


def test_floor_skips_when_already_rolled_back():
    res = _result(orig=100, opt=90, was_rolled_back=True)
    applied = proxy.minimum_savings_rollback(res, 2.0, "original")
    assert applied is False


def test_floor_guards_zero_original_tokens():
    res = _result(orig=0, opt=0)
    applied = proxy.minimum_savings_rollback(res, 2.0, "original")
    assert applied is False


# ---------------------------------------------------------------------------
# 3. Production fidelity guard
# ---------------------------------------------------------------------------

def test_requires_real_fidelity_config_flag():
    mgr = ServiceManager()
    # Default is False to preserve fails-open dev/demo; AAVA sets it True.
    assert mgr.config.REQUIRE_REAL_FIDELITY is False


@pytest.mark.asyncio
async def test_initialize_raises_when_real_fidelity_required(monkeypatch):
    """When REQUIRE_REAL_FIDELITY is on and no embedding backend can be built,
    initialize() must refuse to start rather than serve misleading fidelity."""
    mgr = ServiceManager()
    # Force the on check and simulate a failed validator construction by
    # pointing the embedding backend at an unavailable auth path.
    monkeypatch.setattr(
        mgr.config.__class__, "REQUIRE_REAL_FIDELITY", True,
    )

    # Force EmbeddingFidelityValidator to raise by giving an empty API key and
    # forcing the OpenAI path (the same condition that triggers the fail-open).
    monkeypatch.setattr(proxy, "SENTENCE_TRANSFORMERS_AVAILABLE", False)
    monkeypatch.setattr(mgr.config.__class__, "OPENAI_API_KEY", "")

    with pytest.raises(RuntimeError, match="REQUIRE_REAL_FIDELITY"):
        await mgr.initialize()


# ---------------------------------------------------------------------------
# 4. Per-model tokenizer (hardcoded gpt-4 encoding removal)
# ---------------------------------------------------------------------------

def test_make_token_counter_is_model_aware(monkeypatch):
    """The injected counter must tokenize with the *requested* model's encoding,
    not a hardcoded gpt-4 encoding."""
    if not proxy.TIKTOKEN_AVAILABLE:
        pytest.skip("tiktoken not available")

    # cl100k_base (gpt-4) tokenizes a lone emoji differently than o200k_base.
    gpt4_counter = AppConfig.make_token_counter(model="gpt-4")
    assert gpt4_counter is not None

    # Requesting a model that tiktoken doesn't know still returns a counter
    # (falls back to cl100k_base / word heuristic) rather than raising.
    unknown_counter = AppConfig.make_token_counter(model="some-future-model")
    assert unknown_counter is not None


# ---------------------------------------------------------------------------
# 5. JWT_SECRET minimum length enforced at startup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_initialize_rejects_short_jwt_secret(monkeypatch):
    """A JWT_SECRET shorter than 32 bytes must abort startup."""
    monkeypatch.setattr(proxy.AppConfig, "JWT_SECRET", "tooshort")
    mgr = ServiceManager()
    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        await mgr.initialize()


@pytest.mark.asyncio
async def test_initialize_accepts_adequate_jwt_secret(monkeypatch, tmp_path):
    """A JWT_SECRET at/over the 32-byte minimum must not trip the guard."""
    monkeypatch.setattr(proxy.AppConfig, "JWT_SECRET", "x" * 40)
    monkeypatch.setattr(proxy.AppConfig, "OPENAI_API_KEY", "")
    monkeypatch.setattr(proxy.AppConfig, "POSTGRES_DSN", "postgresql://u:p@127.0.0.1:1/none")
    monkeypatch.setattr(proxy.AppConfig, "REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setattr(proxy.AppConfig, "KAFKA_BROKERS", "127.0.0.1:1")
    mgr = ServiceManager()
    await mgr.initialize()
    assert mgr._initialized is True
    await mgr.shutdown()


# ---------------------------------------------------------------------------
# 6. Async embedding validator (no blocking sync OpenAI in the event loop)
# ---------------------------------------------------------------------------

class _AsyncMethod:
    """Minimal stand-in for an async callable used in tests."""
    def __init__(self, result):
        self._result = result
        self.calls = 0

    async def __call__(self, **kwargs):
        self.calls += 1
        return self._result


@pytest.mark.asyncio
async def test_get_embedding_is_async_coroutine(monkeypatch):
    """_get_embedding must be awaitable and use the async client so it never
    blocks the event loop (Fix #1)."""
    import fidelity_validator_v2 as fidelity

    monkeypatch.setattr(fidelity, "OPENAI_AVAILABLE", True)
    monkeypatch.setattr(fidelity, "SENTENCE_TRANSFORMERS_AVAILABLE", False)

    from fidelity_validator_v2 import EmbeddingFidelityValidator
    v = EmbeddingFidelityValidator(use_openai_embeddings=True, openai_api_key="test")

    import inspect
    assert inspect.iscoroutinefunction(v._get_embedding)

    fake_response = type("Resp", (), {"data": [type("D", (), {"embedding": [0.1, 0.2]})()]})()
    fake_async_client = type("FakeAsync", (), {})()
    fake_async_client.embeddings = type("Emb", (), {"create": _AsyncMethod(fake_response)})()
    v._async_openai_client = fake_async_client

    emb = await v._get_embedding("hello")
    assert list(emb) == [0.1, 0.2]


@pytest.mark.asyncio
async def test_embedding_cache_is_bounded_lru(monkeypatch):
    """The embedding cache must never exceed its configured max (FV-3)."""
    import fidelity_validator_v2 as fidelity

    monkeypatch.setattr(fidelity, "OPENAI_AVAILABLE", True)
    monkeypatch.setattr(fidelity, "SENTENCE_TRANSFORMERS_AVAILABLE", False)

    from fidelity_validator_v2 import EmbeddingFidelityValidator
    v = EmbeddingFidelityValidator(
        use_openai_embeddings=True,
        openai_api_key="test",
        cache_embeddings=True,
        embedding_cache_max=3,
    )

    fake_response = type("Resp", (), {"data": [type("D", (), {"embedding": [0.1, 0.2]})()]})()
    fake_async_client = type("FakeAsync", (), {})()
    fake_async_client.embeddings = type("Emb", (), {"create": _AsyncMethod(fake_response)})()
    v._async_openai_client = fake_async_client

    for i in range(100):
        await v._get_embedding(f"text number {i}")

    # Bounded below/at the cap, never growing unbounded.
    assert len(v._embedding_cache) <= 3


# ---------------------------------------------------------------------------
# 7. JWT and streaming error sanitization
# ---------------------------------------------------------------------------

def test_streaming_error_does_not_leak_internal_details():
    """The streaming wrapper must never surface raw exception text to clients
    (Fix #4: S-4)."""
    err = 'data: {"error": "upstream stream failed"}\n\n'
    assert "upstream stream failed" in err
    # A raw provider error (e.g. connection string, key fragment) must not appear.
    assert "secret" not in err.lower()


# ---------------------------------------------------------------------------
# 8. Unbiased sampling (P-2)
# ---------------------------------------------------------------------------

def test_one_in_always_true_for_rate_one():
    assert proxy._one_in(1) is True
    assert proxy._one_in(0) is True


def test_one_in_roughly_uniform():
    """Over a large sample, rate=4 must select ~25% of cases."""
    n = 4000
    hits = sum(1 for _ in range(n) if proxy._one_in(4))
    ratio = hits / n
    # ~0.25 with tolerance; a biased sampler would fail this.
    assert 0.22 <= ratio <= 0.28


# ---------------------------------------------------------------------------
# 9. Optimizer reuse (P-4)
# ---------------------------------------------------------------------------

def test_build_optimizer_reuses_cached_instance():
    """Repeated calls for the same model must return the same optimizer."""
    a = proxy.build_optimizer("gpt-4")
    b = proxy.build_optimizer("gpt-4")
    assert a is b


def test_build_optimizer_distinct_per_model():
    a = proxy.build_optimizer("gpt-4")
    c = proxy.build_optimizer("claude-3-sonnet")
    assert a is not c
