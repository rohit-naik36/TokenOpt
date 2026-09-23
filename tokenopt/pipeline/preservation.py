"""PreservationMap data model and diagnostic types.

This module defines the foundational data model emitted by the Context Analyzer
as specified in `architecture/context-analyzer-design.md` and governed by the
`architecture/context-preservation-contract.md`.

These data structures represent immutable diagnostic metadata describing
detected structures, invariants, and transformation eligibility. They do NOT
perform compression, rewriting, budget allocation, candidate selection, or
validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class PreservationClass(str, Enum):
    """Preservation classes establishing the monotonic protection hierarchy."""

    P0_AUTHORITY = "P0"  # Authority & protocol protected (no lossy change)
    P1_INFORMATION = "P1"  # Concrete invariants (lexical, semantic, structural)
    P2_COMPRESSIBLE = "P2"  # Meaning-preserving compressible (prose, explanations)
    P3_REMOVABLE = "P3"  # Safely removable (filler, pleasantries, spacing)


class InvariantType(str, Enum):
    """Classification of the integrity requirement for a preserved invariant."""

    LEXICAL = "lexical"  # Exact string literal must survive
    SEMANTIC = "semantic"  # Exact value / meaning must survive
    STRUCTURAL = "structural"  # Grammar / AST syntax must survive


class StructuralType(str, Enum):
    """Content structure types recognized by the Context Analyzer."""

    PROSE = "prose"  # Free-form natural language
    CODE_PYTHON = "code_python"  # Python code block or script
    JSON = "json"  # JSON object or array
    MARKDOWN_TABLE = "markdown_table"  # Tabular Markdown layout
    TOOL_PAYLOAD = "tool_payload"  # Serialized tool call / result


class DetectionCertainty(str, Enum):
    """Certainty level for structure classification."""

    DETECTED = "detected"  # Confirmed structure via grammar/parser
    NOT_DETECTED = "not_detected"  # Confirmed absence of specialized structure
    AMBIGUOUS = "ambiguous"  # Partial syntax, malformed block, or conflict


class EntityCategory(str, Enum):
    """Abstract domains for detected entities and constraints."""

    IDENTIFIER = "identifier"  # Resource/system/cluster IDs, citation tags
    ERROR_CODE = "error_code"  # Hex codes, error tags, exception types
    URL_OR_ENDPOINT = "url_or_endpoint"  # HTTP/HTTPS URLs, endpoints, port specs
    NUMERIC_CONSTRAINT = "numeric_constraint"  # Quantities with units, percentages, counts
    DATETIME_CONSTRAINT = "datetime_constraint"  # ISO dates, quarters, deadlines, timestamps
    NEGATIVE_CONSTRAINT = "negative_constraint"  # Explicit prohibitions ("do not", "never")
    CONFIGURATION_VALUE = "configuration_value"  # Param assignments, environment flags
    SECURITY_COMPLIANCE = "security_compliance"  # Protocols, tokens, auth directives


@dataclass(frozen=True)
class PreservedInvariant:
    """A concrete item that must survive optimization intact."""

    category: EntityCategory
    invariant_type: InvariantType
    marker: str
    message_index: int
    role: str
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize invariant to dictionary representation."""
        return {
            "category": self.category.value if isinstance(self.category, Enum) else self.category,
            "invariant_type": (
                self.invariant_type.value
                if isinstance(self.invariant_type, Enum)
                else self.invariant_type
            ),
            "marker": self.marker,
            "message_index": self.message_index,
            "role": self.role,
            "description": self.description,
        }


@dataclass(frozen=True)
class TransformationEligibility:
    """Defines permitted transformation operations rooted in contract terminology."""

    allow_lossless_normalization: bool = False
    allow_meaning_preserving_compression: bool = False
    allow_removal: bool = False
    allow_truncation: bool = False
    required_validators: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.required_validators, tuple):
            object.__setattr__(
                self,
                "required_validators",
                tuple(self.required_validators),
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize transformation eligibility to dictionary representation."""
        return {
            "allow_lossless_normalization": self.allow_lossless_normalization,
            "allow_meaning_preserving_compression": (
                self.allow_meaning_preserving_compression
            ),
            "allow_removal": self.allow_removal,
            "allow_truncation": self.allow_truncation,
            "required_validators": list(self.required_validators),
        }


@dataclass(frozen=True)
class ContextUnit:
    """A structural block or contextual span within a message.

    In MVP, ContextUnit represents whole messages or discrete structural blocks
    (such as a top-level code fence, JSON payload, or table).

    The `start_char` and `end_char` fields are reserved for future span-level
    decomposition and remain None in MVP.
    """

    message_index: int
    role: str
    structural_type: StructuralType
    detection_certainty: DetectionCertainty
    preservation_class: PreservationClass
    eligibility: TransformationEligibility
    start_char: int | None = None
    end_char: int | None = None
    invariants: tuple[PreservedInvariant, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.invariants, tuple):
            object.__setattr__(self, "invariants", tuple(self.invariants))

    def to_dict(self) -> dict[str, Any]:
        """Serialize context unit to dictionary representation."""
        return {
            "message_index": self.message_index,
            "role": self.role,
            "structural_type": (
                self.structural_type.value
                if isinstance(self.structural_type, Enum)
                else self.structural_type
            ),
            "detection_certainty": (
                self.detection_certainty.value
                if isinstance(self.detection_certainty, Enum)
                else self.detection_certainty
            ),
            "preservation_class": (
                self.preservation_class.value
                if isinstance(self.preservation_class, Enum)
                else self.preservation_class
            ),
            "start_char": self.start_char,
            "end_char": self.end_char,
            "eligibility": self.eligibility.to_dict(),
            "invariants_count": len(self.invariants),
            "invariants": [inv.to_dict() for inv in self.invariants],
        }


@dataclass(frozen=True)
class PreservationMap:
    """Immutable diagnostic map emitted by the Context Analyzer."""

    units: tuple[ContextUnit, ...] = ()
    invariants: tuple[PreservedInvariant, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.units, tuple):
            object.__setattr__(self, "units", tuple(self.units))
        if not isinstance(self.invariants, tuple):
            object.__setattr__(self, "invariants", tuple(self.invariants))

    def get_invariants_for_message(
        self,
        message_index: int,
    ) -> list[PreservedInvariant]:
        """Return all preserved invariants associated with a specific message index."""
        return [
            inv for inv in self.invariants if inv.message_index == message_index
        ]

    def get_units_for_message(self, message_index: int) -> list[ContextUnit]:
        """Return all context units associated with a specific message index."""
        return [u for u in self.units if u.message_index == message_index]

    def to_dict(self) -> dict[str, Any]:
        """Serialize preservation map to dictionary representation."""
        return {
            "invariants_count": len(self.invariants),
            "units_count": len(self.units),
            "invariants": [inv.to_dict() for inv in self.invariants],
            "units": [u.to_dict() for u in self.units],
        }
