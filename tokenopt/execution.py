"""Async execution adapter for the canonical optimizer.

This module bridges the synchronous canonical optimizer to async execution
contexts (e.g., FastAPI proxy) with bounded concurrency admission.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any

from tokenopt.config import TokenOptConfig
from tokenopt.optimizer import CanonicalOptimizer


class OptimizationCapacityExceededError(Exception):
    """Raised when optimization worker capacity is exhausted."""
    pass


class CanonicalOptimizerAdapter:
    """Async adapter for the proxy - wraps the sync canonical core.

    The proxy expects an async optimize() method with specific result fields.
    This adapter bridges the sync canonical core to the proxy's async interface
    without introducing async into the canonical core.
    """

    def __init__(
        self,
        config: TokenOptConfig | None = None,
        executor: concurrent.futures.ThreadPoolExecutor | None = None,
        semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        self._core = CanonicalOptimizer(config)
        self.config = config or TokenOptConfig()
        self._executor = executor
        self._semaphore = semaphore

    async def optimize(
        self,
        messages: list[dict[str, Any]],
        model: str = "gpt-4o",
        optimization_level: str = "standard",
        baseline_response: str | None = None,
        optimized_response: str | None = None,
    ) -> dict[str, Any]:
        """Async adapter matching PromptOptimizer.optimize() interface.

        The canonical core is synchronous; we run it in a thread pool
        to avoid blocking the event loop.
        """

        # Acquire optimization capacity slot with a short timeout.
        # This slot is held for the duration of the actual worker execution,
        # not just the HTTP request. If capacity is unavailable, fail fast.
        if self._semaphore is not None:
            try:
                await asyncio.wait_for(self._semaphore.acquire(), timeout=0.1)
            except asyncio.TimeoutError:
                raise OptimizationCapacityExceededError(
                    "Optimization capacity exhausted. All workers busy."
                ) from None

        loop = asyncio.get_event_loop()

        def _worker() -> dict[str, Any]:
            """Wrapper that releases the semaphore on the event loop when done."""
            try:
                normalized_messages = [
                    {"role": m.get("role", "user"), "content": m.get("content", "")}
                    for m in messages
                ]
                return self._optimize_sync(normalized_messages, model)
            finally:
                # Release the capacity slot on the event loop from the worker thread.
                # This ensures the slot is held for the actual worker lifetime,
                # not just the HTTP request lifetime.
                if self._semaphore is not None:
                    loop.call_soon_threadsafe(self._semaphore.release)

        result: dict[str, Any] = await loop.run_in_executor(self._executor, _worker)

        # Add fields expected by proxy
        result["cache_hit"] = False
        result["techniques"] = result.get("transformer_metrics", {}).get("techniques", [])
        result["fidelity_score"] = 1.0 if result["validation_decision"] == "accept" else 0.0
        result["fidelity_passed"] = result["validation_decision"] == "accept"
        result["fidelity_details"] = {"engine": "canonical"}
        result["was_skipped"] = False
        result["was_rolled_back"] = result.get("rollback_applied", False)
        result["rollback_reason"] = result.get("rollback_reason")

        return result

    def _optimize_sync(self, messages: list[dict], model: str) -> dict:
        """Synchronous optimization for thread pool execution."""
        from tokenopt.pipeline.base import OptimizationContext
        from tokenopt.utils.token_counter import count_message_tokens

        config = self._core.config
        ctx = OptimizationContext(
            messages=messages,
            model=model,
            config=config,
            model_explicit=True,
        )
        ctx = self._core._run_pipeline(ctx)

        return {
            "optimized_prompt": "\n".join(f"{m['role']}: {m['content']}" for m in ctx.messages),
            "optimized_tokens": count_message_tokens(ctx.messages, model=model),
            "original_tokens": ctx.original_token_count,
            "techniques": [],  # populated by transformer metrics
            "validation_decision": ctx.metrics.get("validation_decision", "accept"),
            "rollback_applied": ctx.metrics.get("rollback_applied", False),
            "rollback_reason": ctx.metrics.get("rollback_reason"),
            "transformer_metrics": {
                "compress_count": ctx.metrics.get("transformer_compress_count", 0),
                "remove_count": ctx.metrics.get("transformer_remove_count", 0),
                "protected_count": ctx.metrics.get("transformer_protected_count", 0),
            },
            "validator_metrics": {
                "validation_decision": ctx.metrics.get("validation_decision", "accept"),
                "rollback_applied": ctx.metrics.get("rollback_applied", False),
                "rollback_reason": ctx.metrics.get("rollback_reason"),
            },
            "pipeline_latency_ms": ctx.metrics.get("pipeline_latency_ms", 0.0),
        }
