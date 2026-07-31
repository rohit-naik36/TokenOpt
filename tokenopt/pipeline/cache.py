"""Semantic caching stage for prompt/response reuse."""

from __future__ import annotations

import json
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from tokenopt.pipeline.base import OptimizationContext, PipelineStage
from tokenopt.utils.embeddings import get_embedding_provider, hash_text
from tokenopt.utils.token_counter import count_message_tokens


@dataclass
class CacheEntry:
    """Cached response entry."""
    prompt_hash: str
    prompt_embedding: Any
    messages: list[dict]
    response: Any
    model: str
    token_count: int
    timestamp: float = field(default_factory=time.time)
    hit_count: int = 0


class CacheStage(PipelineStage):
    """Semantic cache for exact and near-duplicate prompts."""

    name = "cache"

    def __init__(self, config: Any = None):
        self.config = config
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._embedding_provider = get_embedding_provider(fallback=True)
        self._redis = None

    def _get_redis(self) -> Any:
        """Lazy-load Redis if configured."""
        if self._redis is None and self.config and self.config.redis_url:
            try:
                import redis
                self._redis = redis.from_url(self.config.redis_url, decode_responses=True)
            except ImportError:
                pass
        return self._redis

    def process(self, ctx: OptimizationContext) -> OptimizationContext:
        # Generate cache key from messages
        cache_key = self._make_cache_key(ctx.messages)
        prompt_embedding = self._embedding_provider.embed_single(
            self._messages_to_text(ctx.messages)
        )

        # Check cache
        cached = self._lookup_cache(cache_key, prompt_embedding, ctx.model)
        if cached:
            ctx.metadata["cache_hit"] = True
            ctx.metadata["cached_response"] = cached.response
            ctx.metrics["cache_hit"] = True
            cached.hit_count += 1
            return ctx

        # Mark for caching after response
        ctx.metadata["cache_key"] = cache_key
        ctx.metadata["prompt_embedding"] = prompt_embedding
        ctx.metrics["cache_hit"] = False
        return ctx

    def store_response(self, ctx: OptimizationContext, response: Any) -> None:
        """Store response in cache after receiving it."""
        cache_key = ctx.metadata.get("cache_key")
        prompt_embedding = ctx.metadata.get("prompt_embedding")

        if not cache_key or prompt_embedding is None:
            return

        entry = CacheEntry(
            prompt_hash=cache_key,
            prompt_embedding=prompt_embedding,
            messages=ctx.original_messages,
            response=response,
            model=ctx.model,
            token_count=count_message_tokens(ctx.original_messages, ctx.model),
        )

        self._store_entry(cache_key, entry)

    def _make_cache_key(self, messages: list[dict]) -> str:
        """Generate deterministic cache key from messages."""
        # Normalize messages for consistent hashing
        normalized = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                normalized.append(f"{msg.get('role', '')}:{content}")
        return hash_text("|".join(normalized))

    def _messages_to_text(self, messages: list[dict]) -> str:
        """Convert messages to single text for embedding."""
        parts = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                parts.append(content)
        return "\n".join(parts)

    def _lookup_cache(self, cache_key: str, prompt_embedding: Any, model: str) -> CacheEntry | None:
        """Look up cache entry by exact key or semantic similarity."""
        # Exact match first
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if time.time() - entry.timestamp < self.config.cache_ttl:
                self._cache.move_to_end(cache_key)
                return entry
            else:
                del self._cache[cache_key]

        # Check Redis
        redis = self._get_redis()
        if redis:
            try:
                data = redis.get(f"tokenopt:cache:{cache_key}")
                if data:
                    entry = json.loads(data)
                    if time.time() - entry["timestamp"] < self.config.cache_ttl:
                        return CacheEntry(**entry)
            except Exception:
                pass

        # Semantic similarity search (in-memory only)
        threshold = self.config.cache_similarity_threshold
        for entry in self._cache.values():
            if entry.model != model:
                continue
            if time.time() - entry.timestamp >= self.config.cache_ttl:
                continue
            similarity = self._embedding_provider.similarity(
                prompt_embedding, entry.prompt_embedding
            )
            if similarity >= threshold:
                self._cache.move_to_end(entry.prompt_hash)
                return entry

        return None

    def _store_entry(self, cache_key: str, entry: CacheEntry) -> None:
        """Store entry in cache with LRU eviction."""
        # In-memory cache
        self._cache[cache_key] = entry
        self._cache.move_to_end(cache_key)

        # Evict if over max size
        while len(self._cache) > self.config.cache_max_size:
            self._cache.popitem(last=False)

        # Redis cache
        redis = self._get_redis()
        if redis:
            try:
                data = {
                    "prompt_hash": entry.prompt_hash,
                    "prompt_embedding": (
                        entry.prompt_embedding.tolist()
                        if hasattr(entry.prompt_embedding, "tolist")
                        else entry.prompt_embedding
                    ),
                    "messages": entry.messages,
                    "response": entry.response,
                    "model": entry.model,
                    "token_count": entry.token_count,
                    "timestamp": entry.timestamp,
                    "hit_count": entry.hit_count,
                }
                redis.setex(
                    f"tokenopt:cache:{cache_key}",
                    self.config.cache_ttl,
                    json.dumps(data, default=str)
                )
            except Exception:
                pass

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()
        redis = self._get_redis()
        if redis:
            try:
                redis.delete(*redis.keys("tokenopt:cache:*"))
            except Exception:
                pass

    def stats(self) -> dict:
        """Get cache statistics."""
        total_hits = sum(e.hit_count for e in self._cache.values())
        return {
            "size": len(self._cache),
            "total_hits": total_hits,
            "hit_rate": total_hits / max(1, len(self._cache) + total_hits),
        }
