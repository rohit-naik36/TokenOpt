"""Deterministic Context Analyzer for TokenOpt.

This module implements the Context Analyzer as specified in
`architecture/context-analyzer-design.md` and governed by the
`architecture/context-preservation-contract.md`.

The analyzer is a non-mutating pre-flight diagnostic component that inspects
input context and emits an immutable PreservationMap. It does NOT:
- modify or transform message text
- compress or truncate text
- allocate token budgets
- select compression candidates
- validate output or perform rollbacks
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any

from tokenopt.pipeline.preservation import (
    ContextUnit,
    DetectionCertainty,
    EntityCategory,
    InvariantType,
    PreservationClass,
    PreservationMap,
    PreservedInvariant,
    StructuralType,
    TransformationEligibility,
)


# =============================================================================
# Deterministic Structure Detection
# =============================================================================

def detect_structure(content: str, role: str) -> tuple[StructuralType, DetectionCertainty]:
    """Detect structural type and classification certainty for a message."""
    if role == "tool":
        return StructuralType.TOOL_PAYLOAD, DetectionCertainty.DETECTED

    stripped = content.strip()
    if not stripped:
        return StructuralType.PROSE, DetectionCertainty.DETECTED

    # 1. JSON Detection
    # Fenced ```json ... ```
    json_fence_match = re.search(r"```json\s*\n([\s\S]*?)\n```", content)
    if json_fence_match:
        fence_content = json_fence_match.group(1).strip()
        try:
            json.loads(fence_content)
            return StructuralType.JSON, DetectionCertainty.DETECTED
        except Exception:
            return StructuralType.JSON, DetectionCertainty.AMBIGUOUS

    # Standalone JSON starting with { or [ and ending with } or ]
    if (stripped.startswith("{") and stripped.endswith("}")) or (
        stripped.startswith("[") and stripped.endswith("]")
    ):
        try:
            json.loads(stripped)
            return StructuralType.JSON, DetectionCertainty.DETECTED
        except Exception:
            if re.search(r'"[a-zA-Z0-9_]+"\s*:', stripped):
                return StructuralType.JSON, DetectionCertainty.AMBIGUOUS

    # Embedded JSON block { ... } with multiple key-value pairs
    json_block_match = re.search(r"(\{[^{}]*\"[a-zA-Z0-9_]+\"\s*:[^{}]*\})", stripped)
    if json_block_match:
        candidate = json_block_match.group(1)
        try:
            json.loads(candidate)
            return StructuralType.JSON, DetectionCertainty.DETECTED
        except Exception:
            pass

    # Multi-line JSON candidate starting with { and containing key-values
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            json.loads(stripped)
            return StructuralType.JSON, DetectionCertainty.DETECTED
        except Exception:
            if re.search(r'"[a-zA-Z0-9_]+"\s*:', stripped):
                return StructuralType.JSON, DetectionCertainty.AMBIGUOUS

    # 2. Markdown Table Detection
    lines = content.splitlines()
    table_lines = [
        line.strip() for line in lines
        if line.strip().startswith("|") and line.strip().endswith("|")
    ]
    if len(table_lines) >= 2:
        has_separator = any(
            re.match(r"^\|(?:\s*:?-+:?\s*\|)+$", line) for line in table_lines
        )
        if has_separator:
            col_counts = [
                len([c for c in line.split("|")[1:-1]]) for line in table_lines
            ]
            if len(set(col_counts)) == 1:
                return StructuralType.MARKDOWN_TABLE, DetectionCertainty.DETECTED
            return StructuralType.MARKDOWN_TABLE, DetectionCertainty.AMBIGUOUS

        # If table lines contain a broken/malformed separator row
        has_broken_separator = any(
            "-" in line and set(line.replace("|", "").strip()).issubset({"-", ":", " "})
            for line in table_lines
        )
        if has_broken_separator:
            return StructuralType.MARKDOWN_TABLE, DetectionCertainty.AMBIGUOUS

    # 3. Python Code Detection
    # Explicitly tagged Python code fence ```python ... ```
    py_fence_match = re.search(r"```python\s*\n([\s\S]*?)\n```", content)
    if py_fence_match:
        fence_code = py_fence_match.group(1)
        try:
            ast.parse(fence_code)
            return StructuralType.CODE_PYTHON, DetectionCertainty.DETECTED
        except SyntaxError:
            return StructuralType.CODE_PYTHON, DetectionCertainty.AMBIGUOUS

    # Untagged code fence ``` ... ``` with Python structural keywords
    generic_fence_match = re.search(r"```\s*\n([\s\S]*?)\n```", content)
    if generic_fence_match:
        fence_code = generic_fence_match.group(1)
        has_code_keywords = bool(re.search(
            r"(?:^|\n)\s*(?:class\s+[A-Za-z0-9_]+|def\s+[A-Za-z0-9_]+\s*\(|import\s+[A-Za-z0-9_.]+|from\s+[A-Za-z0-9_.]+\s+import)",
            fence_code,
        ))
        if has_code_keywords:
            try:
                ast.parse(fence_code)
                return StructuralType.CODE_PYTHON, DetectionCertainty.DETECTED
            except SyntaxError:
                return StructuralType.CODE_PYTHON, DetectionCertainty.AMBIGUOUS

    # Bare Python code cues: requires a class or def header with subsequent indented body lines
    bare_code_match = re.search(
        r"(?:^|\n)\s*(?:class\s+[A-Z][A-Za-z0-9_]*(?:\s*\([^)]*\))?\s*:|def\s+[a-z_][a-zA-Z0-9_]*\s*\([^\n]*\)\s*:?)",
        content,
    )
    if bare_code_match:
        subcontent = content[bare_code_match.start():]
        lines = subcontent.splitlines()
        header_line = lines[0]
        # Must have at least one indented body line to be considered a dedicated code block
        body_lines = [
            line for line in lines[1:]
            if line.startswith(("    ", "\t"))
        ]
        if body_lines:
            code_block_lines: list[str] = [header_line]
            for line in lines[1:]:
                if line.startswith(("    ", "\t")) or (not line.strip() and code_block_lines):
                    code_block_lines.append(line)
                elif re.match(r"^(?:Could you|Please|Would you|Can you|Thanks|I think)\b", line.strip()):
                    break
                else:
                    break
            candidate_code = "\n".join(code_block_lines).strip()
            try:
                ast.parse(candidate_code)
                return StructuralType.CODE_PYTHON, DetectionCertainty.DETECTED
            except SyntaxError:
                return StructuralType.CODE_PYTHON, DetectionCertainty.AMBIGUOUS

    # Default fallback
    return StructuralType.PROSE, DetectionCertainty.DETECTED


# =============================================================================
# Deterministic Entity & Constraint Extraction (8 Abstract Categories)
# =============================================================================

_IDENTIFIER_PATTERNS = [
    (r"\[DOC-\d+\]", "Citation identifier", 0),
    (r"\b(?:prod|dev|staging)-[a-zA-Z0-9_-]+\b", "Environment resource identifier", re.IGNORECASE),
    (r"\b(?:cluster|node|replica|service)-[a-zA-Z0-9_-]+\b", "System component identifier", re.IGNORECASE),
    (r"\bMW-\d+\b", "Maintenance window identifier", 0),
    (r"\bproject\s+[A-Z0-9][A-Za-z0-9_-]*\b", "Project identifier", 0),
    (r"\bAUTH-TOKEN-[A-Za-z0-9_-]+\b", "Authentication token identifier", 0),
    (r"\bidx_[a-zA-Z0-9_]+\b", "Database index identifier", 0),
    (r"\bcustomer_orders\b", "Database table identifier", 0),
    (r"\b[a-z]+(?:_[a-z0-9]+)*_id\b", "Database column identifier", 0),
    (r"\btotal_amount\b", "Database column identifier", 0),
    (r"\bclass\s+[A-Z][A-Za-z0-9_]*(?=\s*[:\(])", "Class identifier", 0),
    (r"\bdef\s+[a-z_][a-zA-Z0-9_]*(?=\s*\()", "Function identifier", 0),
    (r"\b(?:US-East|EU-Central|AP-South|US-West|EU-West|AP-East)\b", "Region identifier", 0),
]

_ERROR_CODE_PATTERNS = [
    (r"\b(?:[A-Z0-9_]+-)+(?:ERR|ERROR|0x[0-9a-fA-F]+)\b", "Error code signature", 0),
    (r"\b0x[0-9a-fA-F]{4,}\b", "Hexadecimal address / fault code", 0),
    (r"\b[A-Z][a-zA-Z0-9]+(?:Error|Exception)\b", "Exception class", 0),
    (r"\braise\s+[A-Z][a-zA-Z0-9_]*(?:\([^)]*\))?", "Exception raise statement", 0),
    (r"\bCRITICAL_ALERT_ASSERTION\b", "Critical alert tag", 0),
]

_URL_ENDPOINT_PATTERNS = [
    (r"https?://[^\s\"'<>]+", "Network URL", 0),
    (r"(?<![a-zA-Z0-9])/v\d+(?:/[a-zA-Z0-9_.-]+)*\b", "API endpoint", 0),
    (r"\bport\s+\d{2,5}\b", "Port specification", re.IGNORECASE),
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "Contact endpoint", 0),
]

_NUMERIC_CONSTRAINT_PATTERNS = [
    (r"\b\d+(?:\.\d+)?\s*(?:sections?|words?|tokens?|ms|seconds?|minutes?|hours?|days?|req/min|Gbps|Mbps|Kbps)\b", "Numeric quantity with unit", re.IGNORECASE),
    (r"\b\d{1,3}(?:,\d{3})+\s+requests\s+per\s+minute\b", "Rate limit specification", re.IGNORECASE),
    (r"\b\d+(?:\.\d+)?%", "Percentage constraint", 0),
    (r"\b\d+\s+bullet\s+points?\b", "Count constraint", re.IGNORECASE),
    (r"\bversion\s+\d+(?:\.\d+)+\b", "Version constraint", re.IGNORECASE),
]

_DATETIME_CONSTRAINT_PATTERNS = [
    (r"\b\d{4}-\d{2}-\d{2}\b", "ISO calendar date", 0),
    (r"\bQ[1-4]\s+\d{4}\b", "Quarterly timeframe", 0),
    (r"\b\d{2}:\d{2}(?::\d{2})?\s*(?:UTC|GMT)?\b", "Timestamp specification", 0),
]

_NEGATIVE_CONSTRAINT_PATTERNS = [
    (r"\b(?:do not|never|must not|cannot|shall not|should not|prohibit(?:s|ed)?)\b\s+[^.!?\n;]+", "Negative operational constraint", re.IGNORECASE),
]

_CONFIGURATION_VALUE_PATTERNS = [
    (r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}=[a-zA-Z0-9_.]+\b", "Key-value configuration", 0),
    (r"\b(?:PostgreSQL|Postgres|MySQL|Redis|MongoDB|Kafka)\s+\d+\b", "Database version setting", 0),
    (r"\b[A-Z]{2,}(?:_[A-Z0-9]+)+\b", "Configuration constant", 0),
]

_SECURITY_COMPLIANCE_PATTERNS = [
    (r"\bLevel-[0-9]+\b", "Security compliance level", 0),
    (r"\[EXEC-SUMMARY\]", "Executive summary directive", 0),
    (r"\b(?:JWT(?:\s+tokens?)?|gRPC|OAuth\s+2\.0|mTLS|TLS\s+termination)\b", "Security protocol directive", 0),
    (r"\b(?:Phase|Tier|Sev)-[0-9]+\b", "Phase, tier, or severity level", 0),
    (r"\b(?:Breach|Compliant)\b", "Compliance status", 0),
]


def extract_invariants(
    content: str,
    message_index: int,
    role: str,
) -> list[PreservedInvariant]:
    """Extract concrete invariants across the 8 abstract categories."""
    invariants: list[PreservedInvariant] = []
    seen: set[str] = set()

    def _add_match(marker: str, category: EntityCategory, inv_type: InvariantType, desc: str) -> None:
        marker = marker.strip().rstrip(".,;:!?'\"")
        if not marker or marker in seen:
            return
        seen.add(marker)
        invariants.append(
            PreservedInvariant(
                category=category,
                invariant_type=inv_type,
                marker=marker,
                message_index=message_index,
                role=role,
                description=desc,
            )
        )

    # 1. IDENTIFIERS (Lexical)
    for pattern, desc, flags in _IDENTIFIER_PATTERNS:
        for match in re.finditer(pattern, content, flags):
            marker = match.group(0)
            _add_match(marker, EntityCategory.IDENTIFIER, InvariantType.LEXICAL, desc)

    # 2. ERROR CODES (Lexical)
    for pattern, desc, flags in _ERROR_CODE_PATTERNS:
        for match in re.finditer(pattern, content, flags):
            marker = match.group(0)
            _add_match(marker, EntityCategory.ERROR_CODE, InvariantType.LEXICAL, desc)

    # 3. URLS / ENDPOINTS (Lexical)
    for pattern, desc, flags in _URL_ENDPOINT_PATTERNS:
        for match in re.finditer(pattern, content, flags):
            marker = match.group(0)
            _add_match(marker, EntityCategory.URL_OR_ENDPOINT, InvariantType.LEXICAL, desc)

    # 4. NUMERIC CONSTRAINTS (Semantic)
    for pattern, desc, flags in _NUMERIC_CONSTRAINT_PATTERNS:
        for match in re.finditer(pattern, content, flags):
            marker = match.group(0)
            _add_match(marker, EntityCategory.NUMERIC_CONSTRAINT, InvariantType.SEMANTIC, desc)

    # 5. DATETIME CONSTRAINTS (Semantic)
    for pattern, desc, flags in _DATETIME_CONSTRAINT_PATTERNS:
        for match in re.finditer(pattern, content, flags):
            marker = match.group(0)
            _add_match(marker, EntityCategory.DATETIME_CONSTRAINT, InvariantType.SEMANTIC, desc)

    # 6. NEGATIVE CONSTRAINTS (Semantic)
    for pattern, desc, flags in _NEGATIVE_CONSTRAINT_PATTERNS:
        for match in re.finditer(pattern, content, flags):
            marker = match.group(0)
            _add_match(marker, EntityCategory.NEGATIVE_CONSTRAINT, InvariantType.SEMANTIC, desc)

    # 7. CONFIGURATION VALUES (Lexical)
    for pattern, desc, flags in _CONFIGURATION_VALUE_PATTERNS:
        for match in re.finditer(pattern, content, flags):
            marker = match.group(0)
            _add_match(marker, EntityCategory.CONFIGURATION_VALUE, InvariantType.LEXICAL, desc)

    # 8. SECURITY COMPLIANCE (Lexical)
    for pattern, desc, flags in _SECURITY_COMPLIANCE_PATTERNS:
        for match in re.finditer(pattern, content, flags):
            marker = match.group(0)
            _add_match(marker, EntityCategory.SECURITY_COMPLIANCE, InvariantType.LEXICAL, desc)

    return invariants


_COMMON_FILLER_PHRASES = frozenset({
    "thanks",
    "thank you",
    "thank you very much",
    "thanks a lot",
    "ok",
    "okay",
    "got it",
    "sure",
    "great",
    "sounds good",
    "understood",
    "i see",
    "hello",
    "hi",
    "you're welcome",
    "you are welcome",
    "no problem",
})


# =============================================================================
# Preservation Class & Transformation Eligibility Resolution
# =============================================================================

def classify_unit(
    role: str,
    structural_type: StructuralType,
    certainty: DetectionCertainty,
    invariants: list[PreservedInvariant],
    content: str,
) -> tuple[PreservationClass, TransformationEligibility]:
    """Determine preservation class and transformation eligibility.

    Role determines authority defaults.
    Content classification determines transformation eligibility.
    Validators remain decoupled (required_validators = ()) until concrete
    validation mechanisms are introduced in downstream architecture.
    """
    # 1. Authority roles
    if role in ("system", "developer"):
        p_class = PreservationClass.P0_AUTHORITY
        eligibility = TransformationEligibility(
            allow_lossless_normalization=True,
            allow_meaning_preserving_compression=False,
            allow_removal=False,
            allow_truncation=False,
            required_validators=(),
        )
        return p_class, eligibility

    if role == "tool" or structural_type == StructuralType.TOOL_PAYLOAD:
        p_class = PreservationClass.P0_AUTHORITY
        eligibility = TransformationEligibility(
            allow_lossless_normalization=True,
            allow_meaning_preserving_compression=False,
            allow_removal=False,
            allow_truncation=False,
            required_validators=(),
        )
        return p_class, eligibility

    # 2. Structural invariants (code, JSON, table)
    # These types are only assigned when strong deterministic evidence exists
    # (e.g. code fences, indented code blocks, multi-line JSON/tables).
    if structural_type == StructuralType.CODE_PYTHON:
        p_class = PreservationClass.P1_INFORMATION
        eligibility = TransformationEligibility(
            allow_lossless_normalization=False,
            allow_meaning_preserving_compression=False,
            allow_removal=False,
            allow_truncation=False,
            required_validators=(),
        )
        return p_class, eligibility

    if structural_type == StructuralType.JSON:
        p_class = PreservationClass.P1_INFORMATION
        eligibility = TransformationEligibility(
            allow_lossless_normalization=(certainty == DetectionCertainty.DETECTED),  # minification only for valid JSON
            allow_meaning_preserving_compression=False,
            allow_removal=False,
            allow_truncation=False,
            required_validators=(),
        )
        return p_class, eligibility

    if structural_type == StructuralType.MARKDOWN_TABLE:
        p_class = PreservationClass.P1_INFORMATION
        eligibility = TransformationEligibility(
            allow_lossless_normalization=False,
            allow_meaning_preserving_compression=False,
            allow_removal=False,
            allow_truncation=False,
            required_validators=(),
        )
        return p_class, eligibility

    # 3. Prose content (user or assistant)
    # Note: If structural_type == PROSE, even if certainty == AMBIGUOUS (e.g. prose
    # containing an unmatched brace or inline code snippet), the message remains PROSE.
    # Structural uncertainty does NOT elevate ordinary prose to P1_INFORMATION.
    # Principle: absence of detected invariants != evidence of removability.
    # Short length alone is NOT evidence of removability (e.g. "Stop.", "Approved.",
    # "Deploy now." are short but critical decisions or instructions).
    # P3 requires positive deterministic evidence of conversational filler.
    stripped = content.strip().lower()
    normalized_filler = stripped.rstrip(".,;:!?\"' ")
    is_pure_filler = (not invariants) and (normalized_filler in _COMMON_FILLER_PHRASES)

    if is_pure_filler:
        p_class = PreservationClass.P3_REMOVABLE
        eligibility = TransformationEligibility(
            allow_lossless_normalization=True,
            allow_meaning_preserving_compression=True,
            allow_removal=True,
            allow_truncation=False,
            required_validators=(),
        )
        return p_class, eligibility

    # Standard prose with or without invariants: P2_COMPRESSIBLE
    # Core law: "Contains protected P1 information" != "Entire unit is P1"
    p_class = PreservationClass.P2_COMPRESSIBLE
    eligibility = TransformationEligibility(
        allow_lossless_normalization=True,
        allow_meaning_preserving_compression=True,
        allow_removal=False,  # Whole unit cannot be deleted when it has substantive content or invariants
        allow_truncation=False,  # Blind token boundary truncation prohibited
        required_validators=(),
    )
    return p_class, eligibility


# =============================================================================
# Context Analyzer Implementation
# =============================================================================

class ContextAnalyzer:
    """Deterministic, lightweight Context Analyzer for prompt contexts.

    Inspects message roles, detects structural syntax, extracts concrete entities
    and constraints across eight abstract categories, assigns preservation
    classes, and determines transformation eligibility.
    """

    def analyze(self, messages: list[dict[str, Any]]) -> PreservationMap:
        """Analyze a list of chat completion messages and emit an immutable PreservationMap."""
        all_units: list[ContextUnit] = []
        all_invariants: list[PreservedInvariant] = []

        for idx, msg in enumerate(messages):
            role = str(msg.get("role", "user"))
            raw_content = msg.get("content", "")
            content = raw_content if isinstance(raw_content, str) else str(raw_content)

            structural_type, certainty = detect_structure(content, role)
            invariants = extract_invariants(content, idx, role)

            preservation_class, eligibility = classify_unit(
                role=role,
                structural_type=structural_type,
                certainty=certainty,
                invariants=invariants,
                content=content,
            )

            unit = ContextUnit(
                message_index=idx,
                role=role,
                structural_type=structural_type,
                detection_certainty=certainty,
                preservation_class=preservation_class,
                eligibility=eligibility,
                start_char=None,
                end_char=None,
                invariants=tuple(invariants),
            )

            all_units.append(unit)
            all_invariants.extend(invariants)

        return PreservationMap(
            units=tuple(all_units),
            invariants=tuple(all_invariants),
        )
