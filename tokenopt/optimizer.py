"""Canonical optimization interface - thin adapter around the validated
preservation-aware pipeline.

This module provides a clean interface to the validated preservation-aware
pipeline (Analyzer → PreservationMap → Planner → Transformer → Validator)
without changing the underlying validated behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline import OptimizationPipeline
from tokenopt.pipeline.base import OptimizationContext


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
    preservation-aware pipeline (Analyzer → Planner → Transformer → Validator).

    This is a thin synchronous adapter around the existing validated
    preservation-aware pipeline. It does NOT change the validated behavior.
    """

    def __init__(self, config: TokenOptConfig | None = None):
        self.config = config or TokenOptConfig()
        # Use the prototype config boundary: Analyzer → Transformer → Validator
        # (Router, Cache, Summarizer, RAG, FewShot disabled per prototype boundary)
        self._pipeline = self._build_pipeline()

    def _build_pipeline(self) -> "OptimizationPipeline":
        """Build the canonical pipeline per prototype boundary."""
        from tokenopt.pipeline import (
            AnalyzerStage,
            TransformerStage,
            ValidatorStage,
        )
        from tokenopt.pipeline.base import OptimizationPipeline

        # Use prototype config boundary: disable Router, Cache, Summarizer, RAG, FewShot
        config = self.config
        stages = [
            AnalyzerStage(config=self.config),
            # RouterStage disabled per prototype boundary
            TransformerStage(config=self.config),
            ValidatorStage(config=self.config),
        ]
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
    ) -> "OptimizationResult":
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
        pipeline = self._build_pipeline()

        # Create optimization context
        from tokenopt.pipeline.base import OptimizationContext
        from tokenopt.utils.token_counter import count_message_tokens

        ctx = OptimizationContext(
            messages=messages,
            model=model,
            config=config,
            model_explicit=True,
        )

        # Run the canonical pipeline
        ctx = self._run_pipeline(ctx)

        # Compute final token count
        from tokenopt.utils.token_counter import count_message_tokens
        final_token_count = count_message_tokens(ctx.messages, model=ctx.model)

        # Determine validation outcome
        validation_decision = ctx.metrics.get("validation_decision", "accept")
        rollback_applied = ctx.metrics.get("rollback_applied", False)
        rollback_reason = ctx.metrics.get("rollback_reason")

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
        validation_decision = ctx.metrics.get("validation_decision", "accept")
        validator_metrics = {
            "validation_decision": validation_decision,
            "rollback_applied": ctx.metrics.get("rollback_applied", False),
            "rollback_reason": ctx.metrics.get("rollback_reason"),
            "invariants_checked": ctx.metrics.get("validation_invariants_checked", 0),
            "invariants_passed": ctx.metrics.get("validation_invariants_passed", 0),
            "invariants_failed": ctx.metrics.get("validation_invariants_failed", 0),
        }

        original_token_count = ctx.original_token_count
        optimized_token_count = count_message_tokens(ctx.messages, model=model)

        return OptimizationResult(
            optimized_messages=ctx.messages,
            original_token_count=ctx.original_token_count,
            optimized_token_count=count_message_tokens(ctx.messages, model=model),
            validation_decision=ctx.metrics.get("validation_decision", "accept"),
            rollback_applied=ctx.metrics.get("rollback_applied", False),
            rollback_reason=ctx.metrics.get("rollback_reason"),
            transformer_metrics=transformer_metrics,
            validator_metrics=validator_metrics,
            pipeline_latency_ms=ctx.metrics.get("pipeline_latency_ms", 0.0),
        )

    def _run_pipeline(self, ctx: "OptimizationContext") -> "OptimizationContext":
        """Run the pipeline with fail-open stage execution."""
        from copy import deepcopy
        from time import perf_counter

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

    def _should_run_stage(self, stage) -> bool:
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


# Compatibility shim for tokenopt-proxy
# The proxy expects an async optimize() method with specific result fields.
# This adapter bridges the sync canonical core to the proxy's async interface.

class CanonicalOptimizerAdapter:
    """Async adapter for the proxy - wraps the sync canonical core.

    The proxy expects an async optimize() method with specific result fields.
    This adapter bridges the sync canonical core to the proxy's async interface
    without introducing async into the canonical core.
    """

    def __init__(self, config: "TokenOptConfig" | None = None):
        from tokenopt.optimizer import CanonicalOptimizer
        self._core = CanonicalOptimizer(config)
        self.config = config or TokenOptConfig()

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
        import asyncio
        import hashlib

        # Build cache key
        full_prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        cache_key = f"{optimization_level}:{hashlib.sha256(full_prompt.encode()).hexdigest()}"

        # Check cache
        # Note: cache integration happens at proxy layer; canonical core doesn't cache

        # Run canonical optimization in thread pool
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self._optimize_sync,
            [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages],
            model,
        )

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
        from copy import deepcopy

        config = self._core.config
        ctx = OptimizationContext(
            messages=messages,
            model=model,
            config=config,
            model_explicit=True,
        )
        ctx = self._run_pipeline(ctx)

        final_token_count = count_message_tokens(ctx.messages, model=model)

        return {
            "optimized_prompt": "\n".join(f"{m['role']}: {m['content']}" for m in ctx.messages),
            "optimized_tokens": count_message_tokens(ctx.messages, model=model),
            "original_tokens": ctx.original_token_count,
            "optimized_tokens": count_message_tokens(ctx.messages, model=model),
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


# Backward compatibility shim for tokenopt-proxy
# The proxy currently imports from tokenopt_optimizer:
#   from tokenopt_optimizer import PromptOptimizer, OptimizerConfig, DegradedFidelityValidator
# We provide a compatibility shim that uses the canonical core.

# In tokenopt/compat.py (new file):
"""
Compatibility shim for tokenopt_optimizer consumers.

This module provides the same interface as tokenopt_optimizer but uses
the canonical core underneath.
"""
from tokenopt.optimizer import CanonicalOptimizer, CanonicalOptimizerAdapter
from tokenopt.config import TokenOptConfig
from tokenopt.config import RoutingRule
from tokenopt.pipeline.preservation import PreservationClass, TransformationEligibility

# Re-export for compatibility
OptimizerConfig = TokenOptConfig
PromptOptimizer = CanonicalOptimizerAdapter
DegradedFidelityValidator = None  # Not used - canonical core has its own validator

__all__ = [
    "PromptOptimizer",
    "OptimizerConfig",
    "DegradedFidelityValidator",
    "TokenOptConfig",
    "RoutingRule",
    "PreservationClass",
    "TransformationEligibility",
]