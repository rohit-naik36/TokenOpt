"""Unit tests for the distributed cache in-memory fallback mode.

These do not require a running Redis; when redis is absent the cache
automatically degrades to its in-memory store.
"""

import pytest

from persistence_layer_v2 import DistributedCache


@pytest.mark.asyncio
async def test_memory_get_set_roundtrip():
    cache = DistributedCache()
    await cache.initialize()

    await cache.set("test", "hello", {"answer": 42}, ttl=60)
    value = await cache.get("test", "hello")
    assert value == {"answer": 42}


@pytest.mark.asyncio
async def test_memory_miss_returns_none():
    cache = DistributedCache()
    await cache.initialize()

    assert await cache.get("test", "missing") is None


@pytest.mark.asyncio
async def test_ttl_expiry():
    cache = DistributedCache()
    await cache.initialize()

    await cache.set("test", "key", "value", ttl=0)
    assert await cache.get("test", "key") is None


def test_make_key_is_deterministic_and_prefixed():
    cache = DistributedCache()
    k1 = cache._make_key("embed", "same data")
    k2 = cache._make_key("embed", "same data")
    assert k1 == k2
    assert k1.startswith("tokenopt:embed:")


def test_serialize_deserialize_roundtrip():
    cache = DistributedCache()
    payload = {"list": [1, 2, 3], "text": "hello", "nested": {"a": True}}
    serialized = cache._serialize(payload)
    # Small payloads are stored as plain JSON
    assert not serialized.startswith("COMPRESSED:")
    assert cache._deserialize(serialized) == payload
