"""Canonical optimization interface - thin adapter around the validated
preservation-aware pipeline.

This module provides a clean interface to the validated preservation-aware
pipeline (Analyzer -> PreservationMap -> Planner -> Transformer -> Validator)
without changing the underlying validated behavior.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline import OptimizationPipeline
from tokenopt.pipeline.base import OptimizationContext
from tokenopt.utils.token_counter import count_message_tokens


@dataclass(frozen=True)
class OptimizationResult:
    """Result of a canonical optimization run.

    Contains only information the canonical optimizer legitimately owns.
    Provider-authoritative token counts must come from the evidence layer.
    """

    optimized_messages: list[dict[str, Any]]
    original_token_count: int
    optimized_token_count: int
    validation_decision: str  # "accept" | "reject"
    rollback_applied: bool
    rollback_reason: str | None
    transformer_metrics: dict[str, Any]
    validator_metrics: dict[str, Any]
    pipeline_latency_ms: float


class CanonicalOptimizer:
    """Canonical optimization interface - thin adapter around the validated
    preservation-aware pipeline (Analyzer -> Planner -> Transformer -> Validator).

    This is a thin synchronous adapter around the existing validated
    preservation-aware pipeline. It does NOT change the validated behavior.
    """

    def __init__(self, config: TokenOptConfig | None = None) -> None:
        self.config = config or TokenOptConfig()
        # Use the prototype config boundary: Analyzer -> Transformer -> Validator
        # (Router, Cache, Summarizer, RAG, FewShot disabled per prototype boundary)
        self._pipeline = self._build_pipeline()

    def _build_pipeline(self) -> OptimizationPipeline:
        """Build the canonical pipeline per prototype boundary."""
        from tokenopt.pipeline import OptimizationPipeline
        from tokenopt.pipeline.analyzer import AnalyzerStage
        from tokenopt.pipeline.transformer import TransformerStage
        from tokenopt.pipeline.validator import ValidatorStage

        stages = [
            AnalyzerStage(config=self.config),
            TransformerStage(config=self.config),
            ValidatorStage(config=self.config),
        ]
        return OptimizationPipeline(stages, config=self.config)

    def optimize(
        self,
        messages: list[dict[str, Any]],
        model: str,
        config: TokenOptConfig | None = None,
    ) -> OptimizationResult:
        """Run the canonical optimization pipeline.

        This is a synchronous method - the canonical core remains synchronous.
        Async behavior is handled at the proxy boundary via an adapter.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Target model name
            config: Optional config override (merges with instance config)

        Returns:
            OptimizationResult with optimization outcome and metadata
        """
        config = config or self.config

        # Create optimization context
        ctx = OptimizationContext(
            messages=messages,
            model=model,
            config=config,
            model_explicit=True,
        )

        # Run the canonical pipeline
        ctx = self._run_pipeline(ctx)

        # Determine validation outcome
        validation_decision = ctx.metrics.get("validation_decision", "accept")

        # Collect transformer metrics
        transformer_metrics = {
            "compress_count": ctx.metrics.get("transformer_compress_count", 0),
            "remove_count": ctx.metrics.get("transformer_remove_count", 0),
            "protected_count": ctx.metrics.get("transformer_protected_count", 0),
            "p2_prose_evaluated": ctx.metrics.get("p2_prose_messages_evaluated", 0),
            "p2_prose_transformed": ctx.metrics.get("p2_prose_messages_transformed", 0),
            "p2_prose_unchanged": ctx.metrics.get("p2_prose_messages_unchanged", 0),
            "sentences_pruned": ctx.metrics.get("sentences_pruned_count", 0),
            "fallbacks": ctx.metrics.get("transform_fallback_count", 0),
        }

        # Validator metrics
        validator_metrics = {
            "validation_decision": validation_decision,
            "rollback_applied": ctx.metrics.get("rollback_applied", False),
            "rollback_reason": ctx.metrics.get("rollback_reason"),
            "invariants_checked": ctx.metrics.get("validation_invariants_checked", 0),
            "invariants_passed": ctx.metrics.get("validation_invariants_passed", 0),
            "invariants_failed": ctx.metrics.get("validation_invariants_failed", 0),
        }

        return OptimizationResult(
            optimized_messages=ctx.messages,
            original_token_count=ctx.original_token_count,
            optimized_token_count=count_message_tokens(ctx.messages, model=ctx.model),
            validation_decision=ctx.metrics.get("validation_decision", "accept"),
            rollback_applied=ctx.metrics.get("rollback_applied", False),
            rollback_reason=ctx.metrics.get("rollback_reason"),
            transformer_metrics=transformer_metrics,
            validator_metrics=validator_metrics,
            pipeline_latency_ms=ctx.metrics.get("pipeline_latency_ms", 0.0),
        )

    def _run_pipeline(self, ctx: OptimizationContext) -> OptimizationContext:
        """Run the pipeline with fail-open stage execution."""
        for stage in self._pipeline.stages:
            if not self._should_run_stage(stage):
                continue

            checkpoint_messages = deepcopy(ctx.messages)
            checkpoint_model = ctx.model
            checkpoint_metadata = deepcopy(ctx.metadata)

            try:
                ctx = stage(ctx)
            except Exception as e:
                ctx.messages = checkpoint_messages
                ctx.model = checkpoint_model
                ctx.metadata = deepcopy(checkpoint_metadata)
                ctx.metrics[f"{stage.name}_error"] = str(e)

        return ctx

    def _should_run_stage(self, stage: Any) -> bool:
        """Return whether a stage is enabled by configuration."""
        stage_name = stage.name
        config = self.config

        if stage_name == "router":
            return config.enable_routing
        if stage_name in ("compressor", "transformer"):
            return config.enable_compression
        if stage_name == "summarizer":
            return config.enable_summarization
        if stage_name == "cache":
            return config.cache_enabled
        if stage_name == "rag":
            return getattr(config, "enable_rag", True)
        if stage_name == "fewshot":
            return getattr(config, "enable_fewshot", True)
        return True
