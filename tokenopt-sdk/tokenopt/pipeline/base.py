"""Base optimization pipeline and stages."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from tokenopt.config import TokenOptConfig
from tokenopt.utils.token_counter import count_message_tokens


@dataclass
class OptimizationContext:
    """Context passed through optimization pipeline stages."""

    messages: list[dict[str, Any]]
    model: str
    config: TokenOptConfig
    model_explicit: bool = False  # caller passed model= to the client
    metadata: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)

    # Original values for comparison
    original_messages: list[dict[str, Any]] = field(default_factory=list)
    original_token_count: int = 0

    def __post_init__(self) -> None:
        if not self.original_messages:
            self.original_messages = [m.copy() for m in self.messages]
        if not self.original_token_count:
            self.original_token_count = count_message_tokens(self.messages, self.model)


class PipelineStage(ABC):
    """Base class for optimization pipeline stages."""

    name: str = "base"

    @abstractmethod
    def process(self, ctx: OptimizationContext) -> OptimizationContext:
        """Process the context through this stage."""
        pass

    def __call__(self, ctx: OptimizationContext) -> OptimizationContext:
        start = time.perf_counter()
        result = self.process(ctx)
        elapsed = time.perf_counter() - start
        result.metrics[f"{self.name}_latency_ms"] = elapsed * 1000
        return result


class OptimizationPipeline:
    """Sequential optimization pipeline."""

    def __init__(self, stages: list[PipelineStage], config: TokenOptConfig):
        self.stages = stages
        self.config = config

    def run(
        self,
        messages: list[dict[str, Any]],
        model: str,
        model_explicit: bool = False,
        **kwargs: Any
    ) -> OptimizationContext:
        """Run the full optimization pipeline."""
        ctx = OptimizationContext(
            messages=messages,
            model=model,
            config=self.config,
            model_explicit=model_explicit,
            metadata=kwargs,
        )

        for stage in self.stages:
            if self._should_run_stage(stage):
                try:
                    ctx = stage(ctx)
                except Exception as e:
                    # Fail open: optimization errors must never break the request
                    ctx.metrics[f"{stage.name}_error"] = str(e)

        # Final metrics
        ctx.metrics["final_token_count"] = count_message_tokens(ctx.messages, ctx.model)
        ctx.metrics["token_reduction"] = (
            ctx.original_token_count - ctx.metrics["final_token_count"]
        )
        ctx.metrics["token_reduction_pct"] = (
            ctx.metrics["token_reduction"] / ctx.original_token_count * 100
            if ctx.original_token_count > 0 else 0
        )

        return ctx

    def _should_run_stage(self, stage: PipelineStage) -> bool:
        """Check if stage should run based on config."""
        stage_config_map = {
            "compressor": self.config.enable_compression,
            "cache": self.config.cache_enabled,
            "router": self.config.enable_routing,
            "summarizer": self.config.enable_summarization,
        }
        return stage_config_map.get(stage.name, True)
