"""Object contracts and interfaces for Adaptive Compression."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class CompressionProfile:
    """Segment-aware profile mapping signals and risk."""

    segment_id: str
    role: str
    token_count: int
    risk_score: float
    compressibility: float
    signals: dict[str, float] = field(default_factory=dict)
    preservation_flags: list[str] = field(default_factory=list)


@dataclass
class CompressionDecision:
    """Decision parameters dictating how a segment should be compressed."""

    target_technique: str
    aggressiveness_ratio: float
    target_tokens: int
    retry_budget: int


@dataclass
class FidelityResult:
    """Lightweight fidelity evaluation result."""

    passed: bool
    overall_score: float
    semantic_similarity: float
    structural_integrity: float
    details: dict[str, Any] = field(default_factory=dict)
    is_passthrough: bool = False


@dataclass
class OptimizationResult:
    """Result of an optimization loop on a single segment."""

    original_text: str
    optimized_text: str
    tokens_saved: int
    iterations: int
    final_fidelity: FidelityResult | None


class Executor(Protocol):
    """Executes compression on a segment based on a decision."""

    def execute(self, text: str, decision: CompressionDecision) -> str: ...


class Evaluator(Protocol):
    """Evaluates the fidelity of a compressed segment."""

    def evaluate(self, original_text: str, optimized_text: str) -> FidelityResult: ...
