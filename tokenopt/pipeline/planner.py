"""Candidate Planner for TokenOpt prompt optimization.

This module implements the Candidate Planner as specified in Checkpoint 4
of the TokenOpt context preservation architecture.

The Candidate Planner is the bridge between the diagnostic PreservationMap
and future transformation stages:
    PreservationMap -> Candidate Planner -> [Transformation]

Its sole responsibility is to inspect context units and their transformation
eligibility to deterministically decide WHAT content is eligible for transformation
(e.g., compressible, removable) and WHAT content is protected from transformation.

It does NOT:
- perform compression, truncation, or text transformation
- modify message text or context structures
- calculate or allocate token budgets or floors
- validate output or execute rollbacks

Lossless Normalization Boundary:
P0/P1 units are not emitted as transformation candidates in Checkpoint 4.
`allow_lossless_normalization` exists in the PreservationMap eligibility model
for future transformation planning, but Checkpoint 4 only produces COMPRESS
and REMOVE candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.preservation import (
    ContextUnit,
    PreservationClass,
    PreservationMap,
    StructuralType,
    TransformationEligibility,
)


class CandidateType(str, Enum):
    """Types of transformation candidates that the planner can designate."""

    COMPRESS = "compress"  # Eligible for meaning-preserving compression
    REMOVE = "remove"  # Eligible for safe removal / pruning


@dataclass(frozen=True)
class CandidateDecision:
    """A context unit designated as eligible for transformation."""

    unit: ContextUnit
    message_index: int
    candidate_type: CandidateType
    preservation_class: PreservationClass
    eligibility: TransformationEligibility
    reason: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize candidate decision to dictionary representation."""
        return {
            "message_index": self.message_index,
            "candidate_type": self.candidate_type.value,
            "preservation_class": self.preservation_class.value,
            "eligibility": self.eligibility.to_dict(),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ProtectedUnit:
    """A context unit designated as protected from lossy transformation or removal."""

    unit: ContextUnit
    message_index: int
    preservation_class: PreservationClass
    reason: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize protected unit to dictionary representation."""
        return {
            "message_index": self.message_index,
            "preservation_class": self.preservation_class.value,
            "reason": self.reason,
            "invariants_count": len(self.unit.invariants),
        }


@dataclass(frozen=True)
class CandidatePlan:
    """Deterministic planning artifact emitted by the CandidatePlanner.

    Explicitly separates transformation candidates from protected units so that
    reviewers and downstream components can inspect all planning decisions
    without inspecting the transformation engine.
    """

    candidates: tuple[CandidateDecision, ...] = ()
    protected_units: tuple[ProtectedUnit, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.candidates, tuple):
            object.__setattr__(self, "candidates", tuple(self.candidates))
        if not isinstance(self.protected_units, tuple):
            object.__setattr__(self, "protected_units", tuple(self.protected_units))

    @property
    def compression_candidates(self) -> tuple[CandidateDecision, ...]:
        """Return all candidates eligible for meaning-preserving compression."""
        return tuple(
            c for c in self.candidates if c.candidate_type == CandidateType.COMPRESS
        )

    @property
    def removal_candidates(self) -> tuple[CandidateDecision, ...]:
        """Return all candidates eligible for removal."""
        return tuple(
            c for c in self.candidates if c.candidate_type == CandidateType.REMOVE
        )

    def get_candidate_for_message(self, message_index: int) -> CandidateDecision | None:
        """Return candidate decision for a message index, if one exists."""
        for c in self.candidates:
            if c.message_index == message_index:
                return c
        return None

    def get_protected_unit_for_message(self, message_index: int) -> ProtectedUnit | None:
        """Return protected unit for a message index, if one exists."""
        for p in self.protected_units:
            if p.message_index == message_index:
                return p
        return None

    def is_protected(self, message_index: int) -> bool:
        """Check whether a message index is protected."""
        return any(p.message_index == message_index for p in self.protected_units)

    def to_dict(self) -> dict[str, Any]:
        """Serialize candidate plan to dictionary representation."""
        return {
            "candidates_count": len(self.candidates),
            "compression_candidates_count": len(self.compression_candidates),
            "removal_candidates_count": len(self.removal_candidates),
            "protected_units_count": len(self.protected_units),
            "candidates": [c.to_dict() for c in self.candidates],
            "protected_units": [p.to_dict() for p in self.protected_units],
        }


class CandidatePlanner:
    """Deterministic, non-mutating planner for transformation eligibility.

    Consumes a PreservationMap, inspects unit preservation classes and explicit
    eligibility flags, and produces an immutable CandidatePlan.
    """

    def __init__(self, config: TokenOptConfig | None = None) -> None:
        self.config = config

    def plan(self, preservation_map: PreservationMap) -> CandidatePlan:
        """Evaluate a PreservationMap and produce a deterministic CandidatePlan."""
        if preservation_map is None:
            raise ValueError("preservation_map must not be None")

        candidates: list[CandidateDecision] = []
        protected_units: list[ProtectedUnit] = []

        for unit in preservation_map.units:
            p_class = unit.preservation_class
            eligibility = unit.eligibility

            if p_class == PreservationClass.P0_AUTHORITY:
                # P0 is NEVER eligible for removal or lossy transformation
                protected_units.append(
                    ProtectedUnit(
                        unit=unit,
                        message_index=unit.message_index,
                        preservation_class=p_class,
                        reason=(
                            "P0_AUTHORITY: Protected protocol/authority unit; "
                            "ineligible for removal or lossy transformation"
                        ),
                    )
                )

            elif p_class == PreservationClass.P1_INFORMATION:
                # P1 is NEVER eligible for removal or lossy transformation
                if unit.structural_type in (
                    StructuralType.CODE_PYTHON,
                    StructuralType.JSON,
                    StructuralType.MARKDOWN_TABLE,
                ):
                    reason = (
                        f"P1_INFORMATION: Protected structural syntax ({unit.structural_type.value}); "
                        "ineligible for removal or lossy transformation"
                    )
                elif unit.invariants:
                    reason = (
                        f"P1_INFORMATION: Protected invariant content ({len(unit.invariants)} invariant(s)); "
                        "ineligible for removal or lossy transformation"
                    )
                else:
                    reason = (
                        "P1_INFORMATION: Protected information unit; "
                        "ineligible for removal or lossy transformation"
                    )

                protected_units.append(
                    ProtectedUnit(
                        unit=unit,
                        message_index=unit.message_index,
                        preservation_class=p_class,
                        reason=reason,
                    )
                )

            elif p_class == PreservationClass.P2_COMPRESSIBLE:
                # P2 may be considered for meaning-preserving compression iff eligibility allows it
                if eligibility.allow_meaning_preserving_compression:
                    candidates.append(
                        CandidateDecision(
                            unit=unit,
                            message_index=unit.message_index,
                            candidate_type=CandidateType.COMPRESS,
                            preservation_class=p_class,
                            eligibility=eligibility,
                            reason="P2_COMPRESSIBLE: Eligible for meaning-preserving compression per eligibility policy",
                        )
                    )
                else:
                    protected_units.append(
                        ProtectedUnit(
                            unit=unit,
                            message_index=unit.message_index,
                            preservation_class=p_class,
                            reason="P2_COMPRESSIBLE: Compression disallowed by transformation eligibility policy",
                        )
                    )

            elif p_class == PreservationClass.P3_REMOVABLE:
                # P3 may be considered for removal iff eligibility allows it
                if eligibility.allow_removal:
                    candidates.append(
                        CandidateDecision(
                            unit=unit,
                            message_index=unit.message_index,
                            candidate_type=CandidateType.REMOVE,
                            preservation_class=p_class,
                            eligibility=eligibility,
                            reason="P3_REMOVABLE: Eligible for removal per eligibility policy",
                        )
                    )
                else:
                    protected_units.append(
                        ProtectedUnit(
                            unit=unit,
                            message_index=unit.message_index,
                            preservation_class=p_class,
                            reason="P3_REMOVABLE: Removal disallowed by transformation eligibility policy",
                        )
                    )

            else:
                # Defensive fallback: unknown classes are protected unconditionally
                protected_units.append(
                    ProtectedUnit(
                        unit=unit,
                        message_index=unit.message_index,
                        preservation_class=p_class,
                        reason=f"UNKNOWN_CLASS ({p_class}): Protected unconditionally by fail-safe policy",
                    )
                )

        return CandidatePlan(
            candidates=tuple(candidates),
            protected_units=tuple(protected_units),
        )

    def __call__(self, preservation_map: PreservationMap) -> CandidatePlan:
        """Allow planner instance to be called directly."""
        return self.plan(preservation_map)
