"""Behavioral contract tests for the semantic cache stage."""

import time

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.base import OptimizationContext
from tokenopt.pipeline.cache import CacheStage


class _ScriptedProvider:
    """Embedding provider with scripted similarity for deterministic tests."""

    def __init__(self, sim_table):
        self._table = sim_table

    def embed(self, texts):
        return list(texts)

    def embed_single(self, text):
        return text

    def similarity(self, a, b):
        return self._table.get((a, b), self._table.get((b, a), 0.0))


class _FakeRedis:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def setex(self, key, ttl, value):
        self.data[key] = value

    def keys(self, pattern="*"):
        prefix = pattern.rstrip("*")
        return [k for k in self.data if k.startswith(prefix)]

    def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)


class _BrokenRedis:
    def __init__(self):
        self.calls = []

    def get(self, key):
        self.calls.append("get")
        raise RuntimeError("redis down")

    def setex(self, key, ttl, value):
        self.calls.append("setex")
        raise RuntimeError("redis down")

    def keys(self, pattern="*"):
        self.calls.append("keys")
        raise RuntimeError("redis down")

    def delete(self, *keys):
        self.calls.append("delete")
        raise RuntimeError("redis down")


def _ctx(messages, config, model="gpt-4o"):
    return OptimizationContext(messages=messages, model=model, config=config)


def _stage(config):
    return CacheStage(config)


def test_name():
    assert CacheStage(TokenOptConfig()).name == "cache"


def test_miss_sets_metadata_and_metric():
    config = TokenOptConfig()
    ctx = _ctx([{"role": "user", "content": "hello world"}], config)
    result = _stage(config).process(ctx)
    assert result.metrics["cache_hit"] is False
    assert "cache_key" in result.metadata
    assert "prompt_embedding" in result.metadata


def test_store_and_exact_hit_roundtrip():
    config = TokenOptConfig()
    stage = _stage(config)
    ctx1 = _ctx([{"role": "user", "content": "hello world"}], config)
    stage.process(ctx1)
    stage.store_response(ctx1, "response-1")

    ctx2 = _ctx([{"role": "user", "content": "hello world"}], config)
    result = stage.process(ctx2)
    assert result.metrics["cache_hit"] is True
    assert result.metadata["cache_hit"] is True
    assert result.metadata["cached_response"] == "response-1"


def test_different_prompts_do_not_cross_hit():
    config = TokenOptConfig()
    stage = _stage(config)
    ctx1 = _ctx([{"role": "user", "content": "hello world"}], config)
    stage.process(ctx1)
    stage.store_response(ctx1, "response-1")

    ctx2 = _ctx([{"role": "user", "content": "goodbye world"}], config)
    result = stage.process(ctx2)
    assert result.metrics["cache_hit"] is False


def test_hit_count_and_stats():
    config = TokenOptConfig()
    stage = _stage(config)
    ctx1 = _ctx([{"role": "user", "content": "hello world"}], config)
    stage.process(ctx1)
    stage.store_response(ctx1, "response-1")
    stage.process(_ctx([{"role": "user", "content": "hello world"}], config))
    assert stage.stats() == {"size": 1, "total_hits": 1, "hit_rate": 0.5}


def test_stats_on_empty_cache():
    stage = _stage(TokenOptConfig())
    assert stage.stats() == {"size": 0, "total_hits": 0, "hit_rate": 0.0}


def test_store_response_without_metadata_is_noop():
    config = TokenOptConfig()
    stage = _stage(config)
    ctx = _ctx([{"role": "user", "content": "hello world"}], config)
    stage.store_response(ctx, "response-1")
    assert stage.stats()["size"] == 0


def test_ttl_expiry_removes_entry():
    config = TokenOptConfig(cache_ttl=60)
    stage = _stage(config)
    ctx = _ctx([{"role": "user", "content": "hello world"}], config)
    stage.process(ctx)
    stage.store_response(ctx, "response-1")
    key = stage._cache.keys().__iter__().__next__()
    stage._cache[key].timestamp = time.time() - 120

    result = stage.process(_ctx([{"role": "user", "content": "hello world"}], config))
    assert result.metrics["cache_hit"] is False
    assert stage.stats()["size"] == 0


def test_lru_eviction_at_max_size():
    config = TokenOptConfig(cache_max_size=2)
    stage = _stage(config)
    for content in ["message A", "message B", "message C"]:
        ctx = _ctx([{"role": "user", "content": content}], config)
        stage.process(ctx)
        stage.store_response(ctx, f"response-{content[-1]}")

    assert stage.stats()["size"] == 2
    result_a = stage.process(_ctx([{"role": "user", "content": "message A"}], config))
    result_b = stage.process(_ctx([{"role": "user", "content": "message B"}], config))
    result_c = stage.process(_ctx([{"role": "user", "content": "message C"}], config))
    assert result_a.metrics["cache_hit"] is False
    assert result_b.metrics["cache_hit"] is True
    assert result_c.metrics["cache_hit"] is True


def test_semantic_hit_above_threshold():
    config = TokenOptConfig(cache_similarity_threshold=0.95)
    stage = _stage(config)
    stage._embedding_provider = _ScriptedProvider({("hello world", "hello world there"): 0.99})

    ctx1 = _ctx([{"role": "user", "content": "hello world"}], config)
    stage.process(ctx1)
    stage.store_response(ctx1, "response-1")

    ctx2 = _ctx([{"role": "user", "content": "hello world there"}], config)
    result = stage.process(ctx2)
    assert result.metrics["cache_hit"] is True
    assert result.metadata["cached_response"] == "response-1"


def test_semantic_miss_below_threshold():
    config = TokenOptConfig(cache_similarity_threshold=0.95)
    stage = _stage(config)
    stage._embedding_provider = _ScriptedProvider({("hello world", "hello world there"): 0.5})

    ctx1 = _ctx([{"role": "user", "content": "hello world"}], config)
    stage.process(ctx1)
    stage.store_response(ctx1, "response-1")

    ctx2 = _ctx([{"role": "user", "content": "hello world there"}], config)
    assert stage.process(ctx2).metrics["cache_hit"] is False


def test_model_mismatch_no_semantic_hit():
    config = TokenOptConfig(cache_similarity_threshold=0.95)
    stage = _stage(config)
    stage._embedding_provider = _ScriptedProvider({("hello world", "hello world there"): 0.99})

    ctx1 = _ctx([{"role": "user", "content": "hello world"}], config, model="gpt-4o")
    stage.process(ctx1)
    stage.store_response(ctx1, "response-1")

    ctx2 = _ctx([{"role": "user", "content": "hello world there"}], config, model="gpt-4o-mini")
    assert stage.process(ctx2).metrics["cache_hit"] is False


def test_expired_entry_skipped_in_semantic_search():
    config = TokenOptConfig(cache_similarity_threshold=0.95, cache_ttl=60)
    stage = _stage(config)
    stage._embedding_provider = _ScriptedProvider({("hello world", "hello world there"): 0.99})

    ctx1 = _ctx([{"role": "user", "content": "hello world"}], config)
    stage.process(ctx1)
    stage.store_response(ctx1, "response-1")
    key = stage._cache.keys().__iter__().__next__()
    stage._cache[key].timestamp = time.time() - 120

    ctx2 = _ctx([{"role": "user", "content": "hello world there"}], config)
    assert stage.process(ctx2).metrics["cache_hit"] is False


def test_non_string_content_does_not_collide_keys():
    config = TokenOptConfig()
    stage = _stage(config)
    ctx1 = _ctx(
        [{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
        config,
    )
    stage.process(ctx1)
    stage.store_response(ctx1, "response-1")

    ctx2 = _ctx(
        [{"role": "user", "content": [{"type": "text", "text": "world"}]}],
        config,
    )
    assert stage.process(ctx2).metrics["cache_hit"] is False


def test_redis_store_and_lookup_roundtrip(monkeypatch):
    config = TokenOptConfig(redis_url="redis://localhost:6379/0")
    stage = _stage(config)
    fake_redis = _FakeRedis()
    monkeypatch.setattr(stage, "_get_redis", lambda: fake_redis)

    ctx = _ctx([{"role": "user", "content": "hello world"}], config)
    stage.process(ctx)
    stage.store_response(ctx, "response-1")
    assert "tokenopt:cache:" in fake_redis.keys("tokenopt:cache:*")[0]

    stage._cache.clear()
    result = stage.process(_ctx([{"role": "user", "content": "hello world"}], config))
    assert result.metrics["cache_hit"] is True
    assert result.metadata["cached_response"] == "response-1"


def test_redis_failure_fails_open(monkeypatch):
    config = TokenOptConfig(redis_url="redis://localhost:6379/0")
    stage = _stage(config)
    broken = _BrokenRedis()
    monkeypatch.setattr(stage, "_get_redis", lambda: broken)

    ctx = _ctx([{"role": "user", "content": "hello world"}], config)
    result = stage.process(ctx)
    assert result.metrics["cache_hit"] is False
    stage.store_response(ctx, "response-1")
    stage.clear()
    assert stage.stats()["size"] == 0


def test_clear_clears_memory_and_redis(monkeypatch):
    config = TokenOptConfig(redis_url="redis://localhost:6379/0")
    stage = _stage(config)
    fake_redis = _FakeRedis()
    monkeypatch.setattr(stage, "_get_redis", lambda: fake_redis)

    for content in ["message A", "message B"]:
        ctx = _ctx([{"role": "user", "content": content}], config)
        stage.process(ctx)
        stage.store_response(ctx, f"response-{content[-1]}")

    stage.clear()
    assert stage.stats()["size"] == 0
    assert fake_redis.keys("tokenopt:cache:*") == []


def test_deterministic_for_identical_inputs():
    config = TokenOptConfig()
    stage = _stage(config)
    ctx1 = _ctx([{"role": "user", "content": "hello world"}], config)
    stage.process(ctx1)
    stage.store_response(ctx1, "response-1")

    first = stage.process(_ctx([{"role": "user", "content": "hello world"}], config))
    second = stage.process(_ctx([{"role": "user", "content": "hello world"}], config))
    assert first.metrics == second.metrics
    assert first.metadata == second.metadata


def test_does_not_mutate_original_messages():
    config = TokenOptConfig()
    stage = _stage(config)
    messages = [{"role": "user", "content": "hello world"}]
    expected = [m.copy() for m in messages]
    ctx = _ctx(messages, config)
    stage.process(ctx)
    stage.store_response(ctx, "response-1")
    assert ctx.original_messages == expected
    assert messages == expected
