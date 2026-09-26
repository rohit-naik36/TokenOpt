"""Compatibility shim for tokenopt_optimizer consumers.

This module provides the same interface as tokenopt_optimizer but uses
the canonical core underneath. This allows tokenopt-proxy to migrate
without changing its import structure.
"""

from tokenopt.config import TokenOptConfig, RoutingRule
from tokenopt.pipeline.preservation import PreservationClass, TransformationEligibility
from typing import Any

from tokenopt.optimizer import CanonicalOptimizer, CanonicalOptimizerAdapter

# Re-export for compatibility
OptimizerConfig = TokenOptConfig
PromptOptimizer = CanonicalOptimizerAdapter

# Provide a DegradedFidelityValidator compatible with tokenopt_optimizer's interface
class DegradedFidelityValidator:
    """Fails-open fidelity validator compatible with tokenopt_optimizer's interface."""
    
    def __init__(self) -> None:
        self._validation_count = 0
    
    async def validate(
        self,
        original_prompt: str = "",
        optimized_prompt: str = "",
        baseline_response: str | None = None,
        optimized_response: str | None = None,
    ) -> Any:
        self._validation_count += 1
        from tokenopt_optimizer import FidelityScore
        return FidelityScore(
            overall=1.0,
            semantic_similarity=1.0,
            structural_similarity=1.0,
            llm_judge_score=None,
            passed=True,
            details={"engine": "degraded_passthrough"},
        )
    
    def get_stats(self) -> dict[str, Any]:
        return {
            "engine": "degraded_passthrough",
            "validations": self._validation_count,
            "note": "No embedding backend configured; fidelity always passes (fails open)",
        }

# Re-export for compatibility
OptimizerConfig = TokenOptConfig
PromptOptimizer = CanonicalOptimizerAdapter
DegradedFidelityValidator = DegradedFidelityValidator

__all__ = [
    "PromptOptimizer",
    "OptimizerConfig",
    "DegradedFidelityValidator",
    "TokenOptConfig",
    "RoutingRule",
    "PreservationClass",
    "TransformationEligibility",
]