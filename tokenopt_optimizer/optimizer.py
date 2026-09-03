"""Prompt optimization core for the TokenOpt optimizer SDK.

``PromptOptimizer`` orchestrates compression + fidelity validation with an
in-process LRU-style cache. It is fully dependency-injected: configuration,
the cache backend, and the fidelity validator are passed in (or defaulted to
safe fallbacks), so the SDK has no dependency on any host application globals.
"""

import asyncio
import hashlib
import inspect
from dataclasses import dataclass
from logging import getLogger
from typing import Any, Protocol, runtime_checkable

from .compressor import SemanticCompressorV2
from .fidelity import DegradedFidelityValidator
from .messages import Message

logger = getLogger("tokenopt.optimizer")


@dataclass
class OptimizerConfig:
    """Tunables that influence how a prompt is optimized."""

    enable_headroom: bool = True
    headroom_target_ratio: float = 0.5
    headroom_min_tokens: int = 100
    headroom_llm_model: str = "gpt-4o"
    cache_enabled: bool = True


@runtime_checkable
class CacheBackend(Protocol):
    """Minimal cache interface the optimizer uses for prompt-result memoization.

    Implementations may be synchronous or async (returning an awaitable from
    ``get``/``set``); the optimizer awaits the result if it is awaitable. This
    lets the SDK work with both in-process dict caches and async backends
    (e.g. a Redis client) with no adapter glue.
    """

    def get(self, prefix: str, key: str) -> Any | None:
        ...

    def set(self, prefix: str, key: str, value: Any, ttl: int | None = None) -> None:
        ...


class _MemoryCache:
    """Tiny in-process fallback cache used when no host cache is supplied."""

    def __init__(self, max_size: int = 4096) -> None:
        self._store: dict[str, Any] = {}
        self._max = max_size

    @staticmethod
    def _build(prefix: str, key: str) -> str:
        return f"{prefix}:{key}"

    def get(self, prefix: str, key: str) -> Any | None:
        return self._store.get(self._build(prefix, key))

    def set(self, prefix: str, key: str, value: Any, ttl: int | None = None) -> None:
        k = self._build(prefix, key)
        if len(self._store) >= self._max:
            self._store.clear()
        self._store[k] = value


class _NoopCache:
    """Cache that neither stores nor returns anything (cache disabled)."""

    def get(self, prefix: str, key: str) -> Any | None:
        return None

    def set(self, prefix: str, key: str, value: Any, ttl: int | None = None) -> None:
        pass


class PromptOptimizer:
    """Production prompt optimization with real fidelity validation.

    Args:
        config: Optimization tunables.
        cache: Optional cache backend implementing ``CacheBackend``. When omitted
            (or when ``cache_enabled`` is False) a small in-process cache is used.
        validator: Optional async fidelity validator implementing
            ``FidelityValidator``. When omitted, a fails-open degraded validator
            is used so optimization never blocks the caller.
        compressor: Optional compressor; defaults to :class:`SemanticCompressorV2`.
    """

    def __init__(
        self,
        config: OptimizerConfig | None = None,
        cache: CacheBackend | None = None,
        validator: Any = None,
        compressor: SemanticCompressorV2 | None = None,
    ) -> None:
        self.config = config or OptimizerConfig()
        self.compressor = compressor or SemanticCompressorV2()
        if self.config.cache_enabled:
            self.cache = cache if cache is not None else _MemoryCache()
        else:
            self.cache = _NoopCache()
        self.validator = validator or DegradedFidelityValidator()

    async def optimize(
        self,
        messages: list[Any],
        optimization_level: str = "standard",
    ) -> dict[str, Any]:
        """Optimize a prompt and validate fidelity.

        ``messages`` may be a list of :class:`Message` objects, dicts with
        ``role``/``content`` keys, or any object exposing those attributes.
        """
        normalized = [Message.from_mapping(m) if not isinstance(m, Message) else m for m in messages]
        full_prompt = "\n".join([f"{m.role}: {m.content}" for m in normalized])
        original_tokens = self._estimate_tokens(full_prompt)

        cache_key = self._cache_key(full_prompt, optimization_level)
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return {
                "optimized_prompt": cached["prompt"],
                "optimized_tokens": cached["tokens"],
                "techniques": ["cache_hit"],
                "cache_hit": True,
                "original_tokens": cached.get("original_tokens", original_tokens),
                "fidelity_score": cached.get("fidelity_score", 1.0),
                "fidelity_passed": cached.get("fidelity_passed", True),
                "fidelity_details": cached.get("fidelity_details", {"engine": "cache_hit"}),
            }

        headroom_enabled = self.config.enable_headroom

        if headroom_enabled:
            hr_compressed, hr_techniques, hr_stats = self.compressor.compress_with_headroom(
                full_prompt,
                optimization_level=optimization_level,
                target_ratio=self.config.headroom_target_ratio,
                min_tokens_to_compress=self.config.headroom_min_tokens,
                llm_model=self.config.headroom_llm_model,
            )
            if hr_techniques and hr_compressed != full_prompt:
                compressed = hr_compressed
                techniques = hr_techniques
                original_tokens = hr_stats.get("tokens_before") or original_tokens
                optimized_tokens = hr_stats.get("tokens_after") or self._estimate_tokens(compressed)
            else:
                compressed, techniques = self.compressor.compress(full_prompt)
                optimized_tokens = self._estimate_tokens(compressed)
        else:
            compressed, techniques = self.compressor.compress(full_prompt)
            optimized_tokens = self._estimate_tokens(compressed)

        fidelity = await self.validator.validate(
            original_prompt=full_prompt,
            optimized_prompt=compressed,
        )

        if not fidelity.passed and techniques:
            compressed = self.compressor.safe_compress(full_prompt)
            optimized_tokens = self._estimate_tokens(compressed)
            techniques = ["safe_compression"]
            fidelity = await self.validator.validate(
                original_prompt=full_prompt,
                optimized_prompt=compressed,
            )

        result = {
            "optimized_prompt": compressed,
            "optimized_tokens": optimized_tokens,
            "techniques": techniques,
            "cache_hit": False,
            "original_tokens": original_tokens,
            "fidelity_score": fidelity.overall,
            "fidelity_passed": fidelity.passed,
            "fidelity_details": fidelity.details,
        }

        if self.config.cache_enabled:
            await self._cache_set(cache_key, {
                "prompt": compressed,
                "tokens": optimized_tokens,
                "original_tokens": original_tokens,
                "fidelity_score": fidelity.overall,
                "fidelity_passed": fidelity.passed,
                "fidelity_details": fidelity.details,
            })

        return result

    def _cache_key(self, prompt: str, optimization_level: str) -> str:
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        return f"{optimization_level}:{digest}"

    async def _cache_get(self, key: str) -> Any | None:
        try:
            result = self.cache.get("optimized_prompt", key)
            if asyncio.iscoroutine(result) or inspect.isawaitable(result):
                return await result
            return result
        except Exception:  # noqa: BLE001 - cache must never break optimization
            return None

    async def _cache_set(self, key: str, value: Any) -> None:
        try:
            result = self.cache.set("optimized_prompt", key, value)
            if asyncio.iscoroutine(result) or inspect.isawaitable(result):
                await result
        except Exception:  # noqa: BLE001, S110 - cache failure is non-fatal
            pass

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return int(len(text.split()) / 0.75)
