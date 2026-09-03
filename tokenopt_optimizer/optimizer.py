"""Prompt optimization core for the TokenOpt optimizer SDK.

``PromptOptimizer`` orchestrates compression + fidelity validation with an
in-process LRU cache with optional TTL. It is fully dependency-injected:
configuration, the cache backend, and the fidelity validator are passed in
(or defaulted to safe fallbacks), so the SDK has no dependency on any host
application globals.
"""

import asyncio
import hashlib
import inspect
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from logging import getLogger
from typing import Any, Protocol, runtime_checkable

from .compressor import SemanticCompressorV2
from .fidelity import DegradedFidelityValidator
from .messages import Message

logger = getLogger("tokenopt.optimizer")


@dataclass(frozen=True)
class OptimizerConfig:
    """Tunables that influence how a prompt is optimized."""

    enable_headroom: bool = True
    headroom_target_ratio: float = 0.5
    headroom_min_tokens: int = 100
    headroom_llm_model: str = "gpt-4o"
    cache_enabled: bool = True
    cache_ttl: int | None = None
    tokenizer: Callable[[str], int] | None = field(default=None, repr=False)
    max_messages: int = 0


@runtime_checkable
class CacheBackend(Protocol):
    """Minimal cache interface the optimizer uses for prompt-result memoization.

    Implementations may be synchronous or async (returning an awaitable from
    ``get``/``set``); the optimizer awaits the result if it is awaitable. This
    lets the SDK work with both in-process dict caches and async backends
    (e.g. a Redis client) with no adapter glue.
    """

    def get(self, prefix: str, key: str) -> Any | None: ...

    def set(self, prefix: str, key: str, value: Any, ttl: int | None = None) -> None: ...


class _MemoryCache:
    """In-process LRU cache with optional TTL, used when no host cache is supplied.

    All public operations are guarded by a lock so the cache is safe to use from
    multiple threads as well as from an asyncio event loop.
    """

    def __init__(self, max_size: int = 4096, default_ttl: int | None = None) -> None:
        self._store: OrderedDict[str, tuple[Any, float | None]] = OrderedDict()
        self._max = max_size
        self._default_ttl = default_ttl
        self._lock = threading.Lock()

    @staticmethod
    def _build(prefix: str, key: str) -> str:
        return f"{prefix}:{key}"

    @staticmethod
    def _is_expired(entry: tuple[Any, float | None]) -> bool:
        _, expires_at = entry
        if expires_at is None:
            return False
        return time.monotonic() >= expires_at

    def get(self, prefix: str, key: str) -> Any | None:
        k = self._build(prefix, key)
        with self._lock:
            entry = self._store.get(k)
            if entry is None:
                return None
            if self._is_expired(entry):
                del self._store[k]
                return None
            self._store.move_to_end(k)
            return entry[0]

    def set(self, prefix: str, key: str, value: Any, ttl: int | None = None) -> None:
        k = self._build(prefix, key)
        effective_ttl = ttl if ttl is not None else self._default_ttl
        expires_at = time.monotonic() + effective_ttl if effective_ttl is not None else None
        with self._lock:
            if k in self._store:
                del self._store[k]
            elif len(self._store) >= self._max:
                self._store.popitem(last=False)
            self._store[k] = (value, expires_at)


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
            (or when ``cache_enabled`` is False) a small in-process LRU cache is used.
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
            self.cache = (
                cache if cache is not None else _MemoryCache(default_ttl=self.config.cache_ttl)
            )
        else:
            self.cache = _NoopCache()
        self.validator = validator or DegradedFidelityValidator()

    async def optimize(
        self,
        messages: list[Any],
        optimization_level: str = "standard",
        baseline_response: str | None = None,
        optimized_response: str | None = None,
    ) -> dict[str, Any]:
        """Optimize a prompt and validate fidelity.

        ``messages`` may be a list of :class:`Message` objects, dicts with
        ``role``/``content`` keys, or any object exposing those attributes.

        ``baseline_response`` and ``optimized_response`` are optional response
        strings passed to the fidelity validator for response-level fidelity
        checking.
        """
        normalized = [
            Message.from_mapping(m) if not isinstance(m, Message) else m for m in messages
        ]

        if self.config.max_messages and len(normalized) > self.config.max_messages:
            normalized = normalized[: self.config.max_messages]

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
            baseline_response=baseline_response,
            optimized_response=optimized_response,
        )

        if not fidelity.passed and techniques:
            compressed = self.compressor.safe_compress(full_prompt)
            optimized_tokens = self._estimate_tokens(compressed)
            techniques = ["safe_compression"]
            fidelity = await self.validator.validate(
                original_prompt=full_prompt,
                optimized_prompt=compressed,
                baseline_response=baseline_response,
                optimized_response=optimized_response,
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
            await self._cache_set(
                cache_key,
                {
                    "prompt": compressed,
                    "tokens": optimized_tokens,
                    "original_tokens": original_tokens,
                    "fidelity_score": fidelity.overall,
                    "fidelity_passed": fidelity.passed,
                    "fidelity_details": fidelity.details,
                },
            )

        return result

    async def optimize_batch(
        self,
        batch: list[list[Any]],
        optimization_level: str = "standard",
        baseline_responses: list[str | None] | None = None,
        optimized_responses: list[str | None] | None = None,
        max_concurrency: int = 4,
    ) -> list[dict[str, Any]]:
        """Optimize a batch of prompts concurrently with a bounded concurrency.

        Each element of ``batch`` is a list of messages (same format as
        :meth:`optimize`). Returns a list of result dicts in the same order.

        ``baseline_responses``/``optimized_responses`` are optional; when
        provided but shorter than ``batch``, missing entries are treated as
        ``None`` (no IndexError). The semaphore caps the number of concurrent
        ``optimize`` calls so a large batch cannot overwhelm the backend.
        """
        baseline_responses = baseline_responses or []
        optimized_responses = optimized_responses or []
        sem = asyncio.Semaphore(max(max_concurrency, 1))

        async def _run(i: int, messages: list[Any]) -> dict[str, Any]:
            br = baseline_responses[i] if i < len(baseline_responses) else None
            or_ = optimized_responses[i] if i < len(optimized_responses) else None
            async with sem:
                return await self.optimize(
                    messages,
                    optimization_level=optimization_level,
                    baseline_response=br,
                    optimized_response=or_,
                )

        return await asyncio.gather(*(_run(i, m) for i, m in enumerate(batch)))

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

    def _estimate_tokens(self, text: str) -> int:
        if self.config.tokenizer is not None:
            return self.config.tokenizer(text)
        return int(len(text.split()) / 0.75)
