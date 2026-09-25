"""Data contracts and schemas for TokenOpt Evidence Harness (Prototype v0.2)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ExecutionStatus(str, Enum):
    """Execution status for paired evaluation run."""

    SUCCESS = "success"
    BASELINE_PROVIDER_ERROR = "baseline_provider_error"
    TOKENOPT_PROVIDER_ERROR = "tokenopt_provider_error"
    VALIDATION_REJECT = "validation_reject"
    VALIDATION_ROLLBACK = "validation_rollback"
    TASK_ASSERTION_FAILED = "task_assertion_failed"
    MALFORMED_PROVIDER_RESPONSE = "malformed_provider_response"


class TaskFidelityStatus(str, Enum):
    """Task fidelity evaluation verdict."""

    PASSED = "passed"
    FAILED = "failed"
    NOT_EVALUATED = "not_evaluated"


@dataclass(frozen=True)
class ExecutionPairKey:
    """Pairing identifier ensuring identical evaluation parameters."""

    case_id: str
    provider: str
    model: str
    generation_parameters: dict[str, Any]


@dataclass
class BaselineEvidence:
    """Observed metrics from unoptimized baseline provider execution."""

    provider_input_tokens: int | None = None
    provider_output_tokens: int | None = None
    provider_total_tokens: int | None = None
    total_latency_ms: float | None = None
    projected_cost: float | None = None
    completion_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TokenOptEvidence:
    """Observed metrics from TokenOpt-optimized execution."""

    estimated_original_tokens: int = 0
    estimated_optimized_tokens: int = 0
    estimated_tokens_saved: int = 0
    provider_input_tokens: int | None = None
    provider_output_tokens: int | None = None
    provider_total_tokens: int | None = None
    total_latency_ms: float | None = None
    pipeline_latency_ms: float | None = None
    model_latency_ms: float | None = None
    projected_cost: float | None = None
    completion_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PreservationEvidence:
    """Preservation metrics extracted directly from TokenOpt ValidatorStage."""

    validation_decision: str = "unknown"
    rollback_applied: bool = False
    rollback_reason: str | None = None
    rollback_violations: list[dict[str, Any]] = field(default_factory=list)
    invariants_checked: int = 0
    invariants_passed: int = 0
    invariants_failed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TaskFidelityEvidence:
    """Task fidelity result for deterministic task assertions."""

    status: TaskFidelityStatus = TaskFidelityStatus.NOT_EVALUATED
    assertion_name: str | None = None
    baseline_passed: bool | None = None
    tokenopt_passed: bool | None = None
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "assertion_name": self.assertion_name,
            "baseline_passed": self.baseline_passed,
            "tokenopt_passed": self.tokenopt_passed,
            "details": self.details,
        }


@dataclass
class SemanticDiagnosticEvidence:
    """Diagnostic semantic similarity between completions."""

    backend: str = "disabled"
    similarity_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ComparisonEvidence:
    """Derived empirical comparison between Baseline and TokenOpt."""

    provider_tokens_saved: int | None = None
    provider_reduction_pct: float | None = None
    projected_cost_saved: float | None = None
    pipeline_overhead_ms: float | None = None
    total_latency_delta_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceRecord:
    """Complete paired evidence record for an evaluation case."""

    run_id: str
    case_id: str
    category: str
    timestamp: str
    provider: str
    model: str
    execution_environment: str  # "cloud_api" or "local_compute"
    generation_parameters: dict[str, Any]
    execution_status: ExecutionStatus
    baseline: BaselineEvidence
    tokenopt: TokenOptEvidence
    preservation: PreservationEvidence
    task_fidelity: TaskFidelityEvidence
    semantic_diagnostics: SemanticDiagnosticEvidence
    comparison: ComparisonEvidence
    error_message: str | None = None
    requested_generation_parameters: dict[str, Any] = field(default_factory=dict)
    effective_generation_parameters: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.requested_generation_parameters and self.generation_parameters:
            self.requested_generation_parameters = dict(self.generation_parameters)
        elif self.requested_generation_parameters and not self.generation_parameters:
            self.generation_parameters = dict(self.requested_generation_parameters)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "case_id": self.case_id,
            "category": self.category,
            "timestamp": self.timestamp,
            "provider": self.provider,
            "model": self.model,
            "execution_environment": self.execution_environment,
            "generation_parameters": dict(self.generation_parameters),
            "requested_generation_parameters": dict(
                self.requested_generation_parameters
                if self.requested_generation_parameters is not None
                else self.generation_parameters
            ),
            "effective_generation_parameters": (
                dict(self.effective_generation_parameters)
                if self.effective_generation_parameters is not None
                else None
            ),
            "execution_status": self.execution_status.value,
            "error_message": self.error_message,
            "baseline": self.baseline.to_dict(),
            "tokenopt": self.tokenopt.to_dict(),
            "preservation": self.preservation.to_dict(),
            "task_fidelity": self.task_fidelity.to_dict(),
            "semantic_diagnostics": self.semantic_diagnostics.to_dict(),
            "comparison": self.comparison.to_dict(),
        }
