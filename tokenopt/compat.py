"""Compatibility shim for tokenopt_optimizer consumers.

This module provides the same interface as tokenopt_optimizer but uses
the canonical core underneath. This allows tokenopt-proxy to migrate
without changing its import structure.
"""

from dataclasses import dataclass
from typing import Any

from tokenopt.config import RoutingRule, TokenOptConfig
from tokenopt.execution import CanonicalOptimizerAdapter
from tokenopt.pipeline.preservation import PreservationClass, TransformationEligibility

# Re-export for compatibility
OptimizerConfig = TokenOptConfig


# Local FidelityScore dataclass matching tokenopt_optimizer.FidelityScore
# This avoids any runtime dependency on the legacy tokenopt_optimizer package.
@dataclass
class FidelityScore:
    """Comprehensive fidelity assessment of an optimized prompt."""

    overall: float
    semantic_similarity: float
    structural_similarity: float
    llm_judge_score: float | None
    passed: bool
    details: dict[str, Any]


# Lazy import to avoid circular dependency
def _get_prompt_optimizer() -> type:
    return CanonicalOptimizerAdapter


PromptOptimizer = _get_prompt_optimizer()


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
    ) -> FidelityScore:
        self._validation_count += 1
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


__all__ = [
    "PromptOptimizer",
    "OptimizerConfig",
    "DegradedFidelityValidator",
    "FidelityScore",
    "TokenOptConfig",
    "RoutingRule",
    "PreservationClass",
    "TransformationEligibility",
]
