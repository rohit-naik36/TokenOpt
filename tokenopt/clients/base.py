"""Base client with optimization pipeline integration."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

from tokenopt.config import TokenOptConfig, get_default_config
from tokenopt.observability import MetricsCollector, RequestMetrics, estimate_cost, get_logger
from tokenopt.pipeline import (
    CacheStage,
    CompressorStage,
    ContextSummarizerStage,
    FewShotSelectorStage,
    OptimizationPipeline,
    RAGOptimizerStage,
    RouterStage,
)


class BaseOptimizedClient(ABC):
    """Base class for optimized LLM clients."""

    def __init__(
        self,
        config: TokenOptConfig | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs: Any
    ):
        self.config = config or get_default_config()
        self.api_key = api_key
        self.base_url = base_url
        self.extra_kwargs = kwargs

        # Initialize observability
        self.metrics_collector = MetricsCollector(
            callback=self.config.metrics_callback
        )
        self.logger = get_logger(f"tokenopt.{self.__class__.__name__.lower()}")

        # Build optimization pipeline
        self.pipeline = self._build_pipeline()

        # Initialize underlying client
        self._client = self._create_client()

    @abstractmethod
    def _create_client(self) -> Any:
        """Create the underlying LLM client."""
        pass

    def _build_pipeline(self) -> OptimizationPipeline:
        """Build the optimization pipeline with all stages."""
        stages = [
            RouterStage(self.config),
            CompressorStage(self.config),
            ContextSummarizerStage(self.config),
            CacheStage(self.config),
            RAGOptimizerStage(self.config),
            FewShotSelectorStage(self.config),
        ]
        return OptimizationPipeline(stages, self.config)

    @abstractmethod
    def _call_api(self, messages: list[dict], model: str, **kwargs: Any) -> Any:
        """Call the underlying LLM API."""
        pass

    @abstractmethod
    def _extract_response_content(self, response: Any) -> str:
        """Extract text content from response."""
        pass

    @abstractmethod
    def _extract_usage(self, response: Any) -> dict[str, int]:
        """Extract token usage from response."""
        pass

    def chat_completion(
        self,
        messages: list[dict],
        model: str | None = None,
        model_explicit: bool | None = None,
        **kwargs: Any
    ) -> Any:
        """Main entry point for chat completions with optimization.

        ``model_explicit`` records whether the caller passed ``model=``;
        it is derived from ``model is not None`` when not given. An
        explicit caller model is never overridden by routing
        (precedence 1, Decision 24).
        """
        start_time = time.perf_counter()
        explicit = model is not None if model_explicit is None else model_explicit
        model = model or self.config.default_model

        # Run optimization pipeline
        pipeline_start = time.perf_counter()
        ctx = self.pipeline.run(messages, model, model_explicit=explicit, **kwargs)
        pipeline_latency = (time.perf_counter() - pipeline_start) * 1000

        # Check for cache hit
        if ctx.metadata.get("cache_hit"):
            cached_response = ctx.metadata["cached_response"]
            self._record_metrics(
                model=ctx.model,
                ctx=ctx,
                pipeline_latency=pipeline_latency,
                total_latency=(time.perf_counter() - start_time) * 1000,
                response=cached_response,
                cache_hit=True
            )
            return cached_response

        # Call API with optimized messages
        try:
            response = self._call_api(ctx.messages, ctx.model, **kwargs)
        except Exception as e:
            self._record_metrics(
                model=ctx.model,
                ctx=ctx,
                pipeline_latency=pipeline_latency,
                total_latency=(time.perf_counter() - start_time) * 1000,
                error=str(e)
            )
            raise

        # Store in cache
        cache_stage = next((s for s in self.pipeline.stages if s.name == "cache"), None)
        if isinstance(cache_stage, CacheStage):
            cache_stage.store_response(ctx, response)

        # Record metrics
        self._record_metrics(
            model=ctx.model,
            ctx=ctx,
            pipeline_latency=pipeline_latency,
            total_latency=(time.perf_counter() - start_time) * 1000,
            response=response,
            cache_hit=False
        )

        return response

    def _record_metrics(
        self,
        model: str,
        ctx: Any,
        pipeline_latency: float,
        total_latency: float,
        response: Any = None,
        cache_hit: bool = False,
        error: str | None = None
    ) -> None:
        """Record request metrics."""
        usage = (
            self._extract_usage(response)
            if response
            else {"prompt_tokens": 0, "completion_tokens": 0}
        )

        optimized_tokens = ctx.metrics.get("final_token_count", ctx.original_token_count)
        tokens_saved = ctx.original_token_count - optimized_tokens

        routing_reason = ctx.metrics.get("routing_rule", "")
        if not routing_reason and "routing_complexity" in ctx.metrics:
            routing_reason = f"complexity-based ({ctx.metrics['routing_complexity']})"
        if not routing_reason and ctx.metrics.get("routing_precedence") == "preserve":
            routing_reason = "preserved (no rule matched)"

        metrics = RequestMetrics(
            model=model,
            original_tokens=ctx.original_token_count,
            optimized_tokens=optimized_tokens,
            output_tokens=usage.get("completion_tokens", 0),
            cache_hit=cache_hit,
            compression_applied=ctx.metrics.get("compression_applied", False),
            compression_attempted=ctx.metrics.get("compression_applied", False),
            compression_effective=tokens_saved > 0,
            tokens_saved=tokens_saved,
            reduction_percentage=(
                tokens_saved / ctx.original_token_count * 100
                if ctx.original_token_count > 0 else 0.0
            ),
            summarization_applied=ctx.metrics.get("summarization_applied", False),
            routing_applied=(
                ctx.metrics.get("routing_applied", False) or "routed_model" in ctx.metrics
            ),
            routing_reason=routing_reason,
            routing_precedence=ctx.metrics.get("routing_precedence", ""),
            rag_optimization_applied=ctx.metrics.get("rag_optimization_applied", False),
            fewshot_applied=ctx.metrics.get("fewshot_applied", False),
            latency_ms=total_latency,
            pipeline_latency_ms=pipeline_latency,
            model_latency_ms=max(0.0, total_latency - pipeline_latency),
            estimated_cost=estimate_cost(
                model, ctx.original_token_count, usage.get("completion_tokens", 0)
            ),
            error=error,
        )

        self.metrics_collector.record(metrics)
        self.logger.log_request(metrics)

    def get_metrics_summary(self) -> dict:
        """Get aggregated metrics summary."""
        return self.metrics_collector.get_summary()

    def clear_cache(self) -> None:
        """Clear the semantic cache."""
        cache_stage = next((s for s in self.pipeline.stages if s.name == "cache"), None)
        if isinstance(cache_stage, CacheStage):
            cache_stage.clear()

    # Delegate attribute access to underlying client
    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)
