"""Metrics and observability for TokenOpt."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class RequestMetrics:
    """Metrics for a single request.

    Token counting semantics:
    - ``original_tokens`` and ``optimized_tokens``: TokenOpt internal token estimates
      calculated using the local tokenizer (tiktoken) before and after pipeline stages.
    - ``output_tokens``: Tokens produced in the completion response (from provider usage).
    - ``provider_input_tokens``: Prompt tokens reported directly by the provider API
      (e.g. OpenAI usage.prompt_tokens or Ollama prompt_eval_count), or None if unavailable.
    - ``provider_output_tokens``: Completion tokens reported directly by the provider API,
      or None if unavailable.

    Cost semantics:
    - ``estimated_cost``: Baseline estimated cost in USD of the UNOPTIMIZED request
      (original input tokens + output tokens).
    - ``optimized_cost``: Estimated cost in USD of the OPTIMIZED request
      (optimized input tokens + output tokens).
    - ``cost_saved``: Estimated cost savings in USD (estimated_cost - optimized_cost).

    ``compression_applied`` reports whether the compressor *stage ran*
    (attempted); whether any token reduction actually occurred is reported
    separately by ``compression_effective`` and ``tokens_saved``, because a
    short prompt may go through compression unchanged.
    """
    timestamp: float = field(default_factory=time.time)
    model: str = ""
    original_tokens: int = 0
    optimized_tokens: int = 0
    output_tokens: int = 0
    provider_input_tokens: int | None = None
    provider_output_tokens: int | None = None
    cache_hit: bool = False
    compression_applied: bool = False
    compression_attempted: bool = False  # compressor stage executed
    compression_effective: bool = False  # tokens were actually reduced
    tokens_saved: int = 0                # original - optimized (may be < 0)
    reduction_percentage: float = 0.0    # tokens_saved / original * 100
    summarization_applied: bool = False
    routing_applied: bool = False
    routing_reason: str = ""  # rule name / complexity fallback / preserved explanation
    routing_precedence: str = ""  # explicit | rule | preserve | complexity | provider_default
    rag_optimization_applied: bool = False
    fewshot_applied: bool = False
    latency_ms: float = 0.0
    pipeline_latency_ms: float = 0.0     # TokenOpt middleware overhead
    model_latency_ms: float = 0.0        # inference time (total - overhead)
    estimated_cost: float = 0.0          # baseline unoptimized cost
    optimized_cost: float = 0.0          # post-optimization cost
    cost_saved: float = 0.0              # estimated_cost - optimized_cost
    validation_decision: str = ""
    rollback_applied: bool = False
    error: str | None = None


class MetricsCollector:
    """Collects and aggregates request metrics."""

    def __init__(self, callback: Callable[[RequestMetrics], None] | None = None):
        self.callback = callback
        self._metrics: list[RequestMetrics] = []
        self._lock = Lock()
        self._counters = {
            "total_requests": 0,
            "cache_hits": 0,
            "compression_count": 0,
            "summarization_count": 0,
            "routing_count": 0,
            "errors": 0,
        }

    def record(self, metrics: RequestMetrics) -> None:
        """Record a request's metrics."""
        with self._lock:
            self._metrics.append(metrics)
            self._counters["total_requests"] += 1

            if metrics.cache_hit:
                self._counters["cache_hits"] += 1
            if metrics.compression_applied:
                self._counters["compression_count"] += 1
            if metrics.summarization_applied:
                self._counters["summarization_count"] += 1
            if metrics.routing_applied:
                self._counters["routing_count"] += 1
            if metrics.error:
                self._counters["errors"] += 1

            if self.callback:
                try:
                    self.callback(metrics)
                except Exception:
                    pass  # Don't let metrics break the main flow

    def get_summary(self) -> dict[str, Any]:
        """Get aggregated metrics summary."""
        with self._lock:
            if not self._metrics:
                return {"total_requests": 0}

            total = len(self._metrics)
            cache_hit_rate = self._counters["cache_hits"] / max(1, total)
            avg_token_reduction = sum(
                m.original_tokens - m.optimized_tokens for m in self._metrics
            ) / total
            avg_latency = sum(m.latency_ms for m in self._metrics) / total
            total_cost = sum(m.estimated_cost for m in self._metrics)
            total_optimized_cost = sum(m.optimized_cost for m in self._metrics)
            total_cost_saved = sum(m.cost_saved for m in self._metrics)

            return {
                "total_requests": total,
                "cache_hit_rate": cache_hit_rate,
                "avg_token_reduction": avg_token_reduction,
                "avg_token_reduction_pct": (
                    avg_token_reduction
                    / max(1, sum(m.original_tokens for m in self._metrics) / total)
                    * 100
                ),
                "avg_latency_ms": avg_latency,
                "total_estimated_cost": total_cost,
                "total_optimized_cost": total_optimized_cost,
                "total_cost_saved": total_cost_saved,
                "error_rate": self._counters["errors"] / max(1, total),
                "optimization_usage": {
                    "compression": self._counters["compression_count"],
                    "summarization": self._counters["summarization_count"],
                    "routing": self._counters["routing_count"],
                },
            }

    def get_recent(self, n: int = 100) -> list[RequestMetrics]:
        """Get most recent N metrics."""
        with self._lock:
            return self._metrics[-n:]

    def clear(self) -> None:
        """Clear all metrics."""
        with self._lock:
            self._metrics.clear()
            for k in self._counters:
                self._counters[k] = 0


# Cost estimation per 1M tokens (approximate, update as needed)
MODEL_COSTS = {
    "gpt-4o": {"input": 5.00, "output": 15.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "o1-preview": {"input": 15.00, "output": 60.00},
    "o1-mini": {"input": 3.00, "output": 12.00},
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku": {"input": 0.25, "output": 1.25},
    "claude-3-opus": {"input": 15.00, "output": 75.00},
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD for a request."""
    costs = MODEL_COSTS.get(model, {"input": 0, "output": 0})
    input_cost = (input_tokens / 1_000_000) * costs["input"]
    output_cost = (output_tokens / 1_000_000) * costs["output"]
    return input_cost + output_cost
