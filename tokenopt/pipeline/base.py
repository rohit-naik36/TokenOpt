"""Core pipeline primitives and optimization context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.preservation import PreservationMap
from tokenopt.utils.token_counter import count_message_tokens


@dataclass
class OptimizationContext:
    """Mutable state passed through the optimization pipeline."""

    messages: list[dict[str, Any]]
    model: str
    config: TokenOptConfig
    model_explicit: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    original_messages: list[dict[str, Any]] = field(default_factory=list)
    original_token_count: int = 0
    preservation_map: PreservationMap | None = None

    def __post_init__(self) -> None:
        # The pipeline must own its working copy.
        # Stages may transform ctx.messages without mutating the
        # caller-owned message structure.
        self.messages = deepcopy(self.messages)

        # Keep an independent snapshot of the original pipeline input.
        if not self.original_messages:
            self.original_messages = deepcopy(self.messages)

        if not self.original_token_count:
            self.original_token_count = count_message_tokens(
                self.messages,
                self.model,
            )


class PipelineStage(ABC):
    """Base class for all optimization pipeline stages."""

    name = "stage"

    def __init__(self, config: TokenOptConfig | None = None):
        self.config = config

    def __call__(self, ctx: OptimizationContext) -> OptimizationContext:
        start = perf_counter()

        ctx = self.process(ctx)

        elapsed_ms = (perf_counter() - start) * 1000
        ctx.metrics[f"{self.name}_latency_ms"] = elapsed_ms

        return ctx

    @abstractmethod
    def process(self, ctx: OptimizationContext) -> OptimizationContext:
        """Process the context through this stage."""
        raise NotImplementedError


class OptimizationPipeline:
    """Executes configured optimization stages with fail-open behavior."""

    def __init__(
        self,
        stages: list[PipelineStage],
        config: TokenOptConfig,
    ):
        self.stages = stages
        self.config = config

    def run(
        self,
        messages: list[dict[str, Any]],
        model: str,
        model_explicit: bool = False,
        **metadata: Any,
    ) -> OptimizationContext:
        ctx = OptimizationContext(
            messages=messages,
            model=model,
            config=self.config,
            model_explicit=model_explicit,
            metadata=metadata,
        )

        for stage in self.stages:
            if not self._should_run_stage(stage):
                continue

            # Deep checkpoint because message content can contain nested
            # dictionaries/lists/structured content blocks.
            checkpoint_messages = deepcopy(ctx.messages)
            checkpoint_model = ctx.model
            checkpoint_metadata = deepcopy(ctx.metadata)

            try:
                ctx = stage(ctx)

            except Exception as e:
                # Restore all mutable state owned by the failed stage.
                #
                # Metrics are deliberately preserved so the failure remains
                # visible to observability and callers.
                ctx.messages = checkpoint_messages
                ctx.model = checkpoint_model
                ctx.metadata = checkpoint_metadata
                ctx.metrics[f"{stage.name}_error"] = str(e)

        final_token_count = count_message_tokens(
            ctx.messages,
            ctx.model,
        )

        ctx.metrics["original_token_count"] = ctx.original_token_count
        ctx.metrics["optimized_token_count"] = final_token_count
        ctx.metrics["tokens_saved"] = (
            ctx.original_token_count - final_token_count
        )

        return ctx

    def _should_run_stage(self, stage: PipelineStage) -> bool:
        """Return whether a stage is enabled by configuration."""

        stage_name = stage.name

        if stage_name == "router":
            return self.config.enable_routing

        if stage_name in ("compressor", "transformer"):
            return self.config.enable_compression

        if stage_name == "summarizer":
            return self.config.enable_summarization

        if stage_name == "cache":
            return self.config.cache_enabled

        if stage_name == "rag":
            return getattr(self.config, "enable_rag", True)

        if stage_name == "fewshot":
            return getattr(self.config, "enable_fewshot", True)

        return True
