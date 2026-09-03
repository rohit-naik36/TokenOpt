"""Fidelity assessment primitives for the TokenOpt optimizer SDK.

This module is intentionally dependency-light: ``FidelityScore`` and the
fails-open ``DegradedFidelityValidator`` require only the standard library.
The heavy embedding-based validator lives in the host application (see
``fidelity_validator_v2.EmbeddingFidelityValidator``) and implements the
``FidelityValidator`` protocol defined here.
"""

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class FidelityScore:
    """Comprehensive fidelity assessment of an optimized prompt."""

    overall: float  # 0-1 composite score
    semantic_similarity: float  # Embedding cosine similarity
    structural_similarity: float  # Format/structure match
    llm_judge_score: float | None  # LLM-as-judge evaluation
    passed: bool
    details: dict[str, Any]


@runtime_checkable
class FidelityValidator(Protocol):
    """Interface the optimizer uses to validate fidelity.

    Any valid implementation must expose an async ``validate`` that accepts
    ``original_prompt``/``optimized_prompt`` (and optionally the response pair)
    and returns a :class:`FidelityScore`.
    """

    async def validate(
        self,
        original_prompt: str,
        optimized_prompt: str,
        baseline_response: str | None = None,
        optimized_response: str | None = None,
    ) -> FidelityScore: ...

    def get_stats(self) -> dict[str, Any]: ...


class DegradedFidelityValidator:
    """Fails-open fidelity validator used when no embedding backend is available.

    Always passes validation (score 1.0) so optimization never blocks the
    request path. Swap in a real validator by configuring an embedding
    backend (sentence-transformers or an OpenAI-compatible embedding key).
    """

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
