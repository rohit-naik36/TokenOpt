"""Deterministic closed-loop validation and rollback stage for TokenOpt.

This module implements the Validation Control Boundary as specified in
Checkpoint 6 of the TokenOpt context preservation architecture.

Architectural invariants:
    1. "The Validator is a verification gate. It is NOT an optimizer."
    2. "The Validator executes only deterministic checks against the
       PreservationMap and structural syntax rules. It does not decide
       what is safe to transform, rewrite text, or perform adaptive loops."
    3. "If preservation obligations cannot be deterministically verified,
       the candidate transformation is REJECTED and the context is fully
       rolled back to the original unmodified representation."

The ValidatorStage:
- Inspects candidate ``ctx.messages`` against ``ctx.original_messages``,
  ``ctx.preservation_map``, and ``ctx.metadata['surviving_indices']``.
- Verifies:
    * Monotonicity and validity of surviving message indices
    * Non-destruction of required turns and system messages
    * Exact survival of P0/P1/P2 lexical invariants in originating roles
    * Structural syntax validity (Python AST, JSON, Markdown tables)
- On ACCEPT:
    * Approves candidate transformation
    * Records validation telemetry
- On REJECT:
    * Atomically rolls back ``ctx.messages = deepcopy(ctx.original_messages)``
    * Resets delivered token savings to zero
    * Preserves attempted savings and violation reasons for observability
"""

from __future__ import annotations

import ast
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Any

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.base import OptimizationContext, PipelineStage
from tokenopt.pipeline.preservation import (
    PreservationClass,
    StructuralType,
)


class ValidationDecision(str, Enum):
    """Outcome decision emitted by the ValidatorStage."""

    ACCEPT = "accept"
    REJECT = "reject"


@dataclass(frozen=True)
class InvariantViolation:
    """Details of a failed preservation or structural invariant."""

    invariant_name: str
    category: str
    invariant_type: str
    original_message_index: int
    role: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize violation to dictionary representation."""
        return {
            "invariant_name": self.invariant_name,
            "category": self.category,
            "invariant_type": self.invariant_type,
            "original_message_index": self.original_message_index,
            "role": self.role,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ValidationResult:
    """Immutable outcome of candidate transformation validation."""

    passed: bool
    decision: ValidationDecision
    violations: tuple[InvariantViolation, ...] = ()
    checked_invariants_count: int = 0
    passed_invariants_count: int = 0
    failed_invariants_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize validation result to dictionary representation."""
        return {
            "passed": self.passed,
            "decision": self.decision.value,
            "violations": [v.to_dict() for v in self.violations],
            "checked_invariants_count": self.checked_invariants_count,
            "passed_invariants_count": self.passed_invariants_count,
            "failed_invariants_count": self.failed_invariants_count,
        }


# =============================================================================
# Deterministic Structural Syntax Parsers
# =============================================================================

def extract_python_code(text: str) -> str:
    """Extract Python code block from text, supporting fences or inline definitions."""
    fences = re.findall(r"```(?:python)?\s*\n(.*?)(?:```|$)", text, re.DOTALL)
    if fences:
        return str(fences[0])

    lines = text.splitlines()
    code_lines: list[str] = []
    in_code = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("class ", "def ", "import ", "from ")):
            in_code = True
        if in_code:
            # Prose following code block marks end of code snippet
            if stripped.startswith(("Could you", "Please", "What do", "Can you", "Thanks")):
                break
            code_lines.append(line)
    return "\n".join(code_lines)


def validate_python_syntax(text: str) -> bool:
    """Validate Python code syntax using ast.parse."""
    code = extract_python_code(text)
    if not code.strip():
        return False
    try:
        ast.parse(code)
        return True
    except (SyntaxError, IndentationError):
        return False


def extract_json_payload(text: str) -> str | None:
    """Extract JSON object or array payload from text."""
    # Check for fenced JSON first
    fence_match = re.search(r"```json\s*\n([\s\S]*?)(?:\n```|$)", text)
    if fence_match:
        return fence_match.group(1).strip()

    start = -1
    for i, ch in enumerate(text):
        if ch in ("{", "["):
            start = i
            break
    if start == -1:
        return None
    close_ch = "}" if text[start] == "{" else "]"
    end = text.rfind(close_ch)
    if end == -1 or end <= start:
        return text[start:]
    return text[start : end + 1]


def validate_json_syntax(text: str) -> bool:
    """Validate JSON payload using json.loads."""
    payload = extract_json_payload(text)
    if payload is None or not payload.strip():
        return False
    try:
        json.loads(payload)
        return True
    except (json.JSONDecodeError, ValueError):
        return False


def validate_markdown_table_structure(text: str) -> bool:
    """Validate markdown table structure.

    Checks:
    - Consistent column count across all rows.
    - No unterminated rows (each row must begin and end with '|').
    - Presence of a valid separator row.
    - Presence of at least one data row.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    table_lines = [line for line in lines if "|" in line]
    if len(table_lines) < 2:
        return False

    for line in table_lines:
        if not line.startswith("|") or not line.endswith("|"):
            return False

    def parse_row(row_str: str) -> list[str]:
        return row_str[1:-1].split("|")

    header = parse_row(table_lines[0])
    num_cols = len(header)
    if num_cols < 1:
        return False

    separator = parse_row(table_lines[1])
    if len(separator) != num_cols:
        return False
    for cell in separator:
        if not re.match(r"^:?-+:?$", cell.strip()):
            return False

    data_rows = table_lines[2:]
    if not data_rows:
        return False
    for row_str in data_rows:
        row = parse_row(row_str)
        if len(row) != num_cols:
            return False

    return True


def validate_tool_payload(content: Any) -> bool:
    """Validate tool payload structure (valid dictionary, list, or JSON string)."""
    if isinstance(content, (dict, list)):
        return True
    if isinstance(content, str):
        try:
            json.loads(content)
            return True
        except (json.JSONDecodeError, ValueError):
            return False
    return True


# =============================================================================
# ValidatorStage Implementation
# =============================================================================

class ValidatorStage(PipelineStage):
    """Validate candidate transformation against preservation obligations.

    If any deterministic preservation invariant or structural syntax check
    fails, the stage executes a full rollback to ``ctx.original_messages``
    and resets delivered token savings to zero.
    """

    name = "validator"

    def __init__(self, config: TokenOptConfig | None = None) -> None:
        super().__init__(config)
        self.config: TokenOptConfig = config or TokenOptConfig()

    def process(self, ctx: OptimizationContext) -> OptimizationContext:
        """Run closed-loop deterministic validation and enforce rollback if violated."""
        # 1. Check pre-flight applicability
        if ctx.preservation_map is None:
            ctx.metrics["validation_passed"] = True
            ctx.metrics["validation_decision"] = ValidationDecision.ACCEPT.value
            ctx.metrics["rollback_applied"] = False
            ctx.metrics["validation_skipped"] = "no_preservation_map"
            return ctx

        if not ctx.metrics.get("transformer_applied", False):
            ctx.metrics["validation_passed"] = True
            ctx.metrics["validation_decision"] = ValidationDecision.ACCEPT.value
            ctx.metrics["rollback_applied"] = False
            ctx.metrics["validation_skipped"] = "transformer_not_applied"
            return ctx

        # 2. Execute validation with fail-closed exception guard
        try:
            result = self._validate(ctx)
            if not result.passed:
                self._rollback(ctx, result)
            else:
                self._record_accept(ctx, result)
        except Exception as e:
            self._handle_validator_exception(ctx, e)

        return ctx

    def _validate(self, ctx: OptimizationContext) -> ValidationResult:
        """Execute deterministic invariant checks against candidate messages."""
        violations: list[InvariantViolation] = []
        checked_count = 0

        # A. Validate surviving_indices metadata
        surviving_indices = ctx.metadata.get("surviving_indices")
        if not isinstance(surviving_indices, list):
            violations.append(
                InvariantViolation(
                    invariant_name="surviving_indices",
                    category="metadata",
                    invariant_type="structural",
                    original_message_index=-1,
                    role="system",
                    reason="Missing or invalid surviving_indices metadata",
                )
            )
            return ValidationResult(
                passed=False,
                decision=ValidationDecision.REJECT,
                violations=tuple(violations),
                checked_invariants_count=1,
                passed_invariants_count=0,
                failed_invariants_count=1,
            )

        # Check element types, bounds, and strict monotonicity
        if len(surviving_indices) != len(ctx.messages):
            violations.append(
                InvariantViolation(
                    invariant_name="surviving_indices_length",
                    category="metadata",
                    invariant_type="structural",
                    original_message_index=-1,
                    role="system",
                    reason=(
                        f"surviving_indices length ({len(surviving_indices)}) "
                        f"mismatches messages length ({len(ctx.messages)})"
                    ),
                )
            )
            return ValidationResult(
                passed=False,
                decision=ValidationDecision.REJECT,
                violations=tuple(violations),
                checked_invariants_count=1,
                passed_invariants_count=0,
                failed_invariants_count=1,
            )

        num_orig = len(ctx.original_messages)
        is_monotonic = True
        for i, idx in enumerate(surviving_indices):
            if not isinstance(idx, int) or idx < 0 or idx >= num_orig:
                is_monotonic = False
                break
            if i > 0 and idx <= surviving_indices[i - 1]:
                is_monotonic = False
                break

        if not is_monotonic:
            violations.append(
                InvariantViolation(
                    invariant_name="surviving_indices_monotonicity",
                    category="metadata",
                    invariant_type="structural",
                    original_message_index=-1,
                    role="system",
                    reason="surviving_indices elements are out of bounds or not strictly monotonic",
                )
            )
            return ValidationResult(
                passed=False,
                decision=ValidationDecision.REJECT,
                violations=tuple(violations),
                checked_invariants_count=1,
                passed_invariants_count=0,
                failed_invariants_count=1,
            )

        # B. Check Turn Non-Destruction
        if num_orig > 0 and len(ctx.messages) == 0:
            violations.append(
                InvariantViolation(
                    invariant_name="turn_non_destruction",
                    category="turn",
                    invariant_type="role",
                    original_message_index=-1,
                    role="all",
                    reason="All messages were removed from non-empty context",
                )
            )

        # C. Check System Message Protection
        orig_sys_indices = [
            i for i, m in enumerate(ctx.original_messages) if m.get("role") == "system"
        ]
        for sys_idx in orig_sys_indices:
            checked_count += 1
            if sys_idx not in surviving_indices:
                violations.append(
                    InvariantViolation(
                        invariant_name="system_message_protection",
                        category="authority",
                        invariant_type="role",
                        original_message_index=sys_idx,
                        role="system",
                        reason=f"System message at original index {sys_idx} was removed",
                    )
                )

        # D. Check Role Invariance on Surviving Messages
        for out_idx, orig_idx in enumerate(surviving_indices):
            checked_count += 1
            cand_role = ctx.messages[out_idx].get("role")
            orig_role = ctx.original_messages[orig_idx].get("role")
            if cand_role != orig_role:
                violations.append(
                    InvariantViolation(
                        invariant_name="role_integrity",
                        category="role",
                        invariant_type="role",
                        original_message_index=orig_idx,
                        role=orig_role or "",
                        reason=(
                            f"Message at original index {orig_idx} had role changed "
                            f"from '{orig_role}' to '{cand_role}'"
                        ),
                    )
                )

        # E. Check Structural Invariants from PreservationMap units
        if ctx.preservation_map is not None:
            for unit in ctx.preservation_map.units:
                orig_idx = unit.message_index
                stype = unit.structural_type

                if stype == StructuralType.CODE_PYTHON:
                    checked_count += 1
                    if orig_idx not in surviving_indices:
                        if unit.preservation_class in (
                            PreservationClass.P0_AUTHORITY,
                            PreservationClass.P1_INFORMATION,
                        ):
                            violations.append(
                                InvariantViolation(
                                    invariant_name="python_code_syntax",
                                    category="structural",
                                    invariant_type="structural",
                                    original_message_index=orig_idx,
                                    role=unit.role,
                                    reason=(
                                        f"Protected Python code at index {orig_idx} was removed"
                                    ),
                                )
                            )
                    else:
                        out_idx = surviving_indices.index(orig_idx)
                        text = ctx.messages[out_idx].get("content", "")
                        if not isinstance(text, str) or not validate_python_syntax(text):
                            violations.append(
                                InvariantViolation(
                                    invariant_name="python_code_syntax",
                                    category="structural",
                                    invariant_type="structural",
                                    original_message_index=orig_idx,
                                    role=unit.role,
                                    reason=(
                                        f"Python code at index {orig_idx} failed syntax validation"
                                    ),
                                )
                            )

                elif stype == StructuralType.JSON:
                    checked_count += 1
                    if orig_idx not in surviving_indices:
                        if unit.preservation_class in (
                            PreservationClass.P0_AUTHORITY,
                            PreservationClass.P1_INFORMATION,
                        ):
                            violations.append(
                                InvariantViolation(
                                    invariant_name="json_syntax",
                                    category="structural",
                                    invariant_type="structural",
                                    original_message_index=orig_idx,
                                    role=unit.role,
                                    reason=f"Protected JSON at index {orig_idx} was removed",
                                )
                            )
                    else:
                        out_idx = surviving_indices.index(orig_idx)
                        text = ctx.messages[out_idx].get("content", "")
                        if not isinstance(text, str) or not validate_json_syntax(text):
                            violations.append(
                                InvariantViolation(
                                    invariant_name="json_syntax",
                                    category="structural",
                                    invariant_type="structural",
                                    original_message_index=orig_idx,
                                    role=unit.role,
                                    reason=f"JSON at index {orig_idx} failed syntax validation",
                                )
                            )

                elif stype == StructuralType.MARKDOWN_TABLE:
                    checked_count += 1
                    if orig_idx not in surviving_indices:
                        if unit.preservation_class in (
                            PreservationClass.P0_AUTHORITY,
                            PreservationClass.P1_INFORMATION,
                        ):
                            violations.append(
                                InvariantViolation(
                                    invariant_name="markdown_table_structure",
                                    category="structural",
                                    invariant_type="structural",
                                    original_message_index=orig_idx,
                                    role=unit.role,
                                    reason=(
                                        f"Protected Markdown table at index {orig_idx} was removed"
                                    ),
                                )
                            )
                    else:
                        out_idx = surviving_indices.index(orig_idx)
                        text = ctx.messages[out_idx].get("content", "")
                        if not isinstance(text, str) or not validate_markdown_table_structure(text):
                            violations.append(
                                InvariantViolation(
                                    invariant_name="markdown_table_structure",
                                    category="structural",
                                    invariant_type="structural",
                                    original_message_index=orig_idx,
                                    role=unit.role,
                                    reason=(
                                        f"Markdown table at index {orig_idx} failed validation"
                                    ),
                                )
                            )

                elif stype == StructuralType.TOOL_PAYLOAD:
                    checked_count += 1
                    if orig_idx in surviving_indices:
                        out_idx = surviving_indices.index(orig_idx)
                        content = ctx.messages[out_idx].get("content", "")
                        if not validate_tool_payload(content):
                            violations.append(
                                InvariantViolation(
                                    invariant_name="tool_payload_syntax",
                                    category="structural",
                                    invariant_type="structural",
                                    original_message_index=orig_idx,
                                    role=unit.role,
                                    reason=(
                                        f"Tool payload at index {orig_idx} failed syntax validation"
                                    ),
                                )
                            )

            # F. Check Lexical Invariants from PreservationMap invariants
            for invariant in ctx.preservation_map.invariants:
                checked_count += 1
                orig_idx = invariant.message_index
                category_val = (
                    invariant.category.value
                    if hasattr(invariant.category, "value")
                    else str(invariant.category)
                )
                inv_type_val = (
                    invariant.invariant_type.value
                    if hasattr(invariant.invariant_type, "value")
                    else str(invariant.invariant_type)
                )

                if orig_idx not in surviving_indices:
                    violations.append(
                        InvariantViolation(
                            invariant_name=invariant.marker,
                            category=category_val,
                            invariant_type=inv_type_val,
                            original_message_index=orig_idx,
                            role=invariant.role,
                            reason=(
                                f"Message {orig_idx} containing invariant "
                                f"'{invariant.marker}' was removed"
                            ),
                        )
                    )
                else:
                    out_idx = surviving_indices.index(orig_idx)
                    cand_msg = ctx.messages[out_idx]
                    cand_role = cand_msg.get("role")

                    if cand_role != invariant.role:
                        violations.append(
                            InvariantViolation(
                                invariant_name=invariant.marker,
                                category=category_val,
                                invariant_type=inv_type_val,
                                original_message_index=orig_idx,
                                role=invariant.role,
                                reason=(
                                    f"Invariant '{invariant.marker}' expected role "
                                    f"'{invariant.role}', found in role '{cand_role}'"
                                ),
                            )
                        )
                    else:
                        cand_content = cand_msg.get("content", "")
                        if not isinstance(cand_content, str):
                            cand_content = str(cand_content)

                        if invariant.marker not in cand_content:
                            violations.append(
                                InvariantViolation(
                                    invariant_name=invariant.marker,
                                    category=category_val,
                                    invariant_type=inv_type_val,
                                    original_message_index=orig_idx,
                                    role=invariant.role,
                                    reason=(
                                        f"Invariant marker '{invariant.marker}' missing from "
                                        f"message at original index {orig_idx}"
                                    ),
                                )
                            )

        passed = len(violations) == 0
        decision = ValidationDecision.ACCEPT if passed else ValidationDecision.REJECT
        failed_count = len(violations)
        passed_count = max(0, checked_count - failed_count)

        return ValidationResult(
            passed=passed,
            decision=decision,
            violations=tuple(violations),
            checked_invariants_count=checked_count,
            passed_invariants_count=passed_count,
            failed_invariants_count=failed_count,
        )

    def _rollback(self, ctx: OptimizationContext, result: ValidationResult) -> None:
        """Execute full atomic rollback to pristine original messages."""
        ctx.messages = deepcopy(ctx.original_messages)

        # Distinguish attempted optimization from delivered optimization
        attempted_tokens = (
            ctx.original_token_count - count_message_tokens_safe(ctx.messages, ctx.model)
            if "optimized_token_count" not in ctx.metrics
            else ctx.original_token_count - ctx.metrics["optimized_token_count"]
        )
        if attempted_tokens > 0:
            ctx.metrics["attempted_tokens_saved"] = attempted_tokens

        primary_reason = (
            f"{result.violations[0].invariant_name}: {result.violations[0].reason}"
            if result.violations
            else "validation_rejected"
        )

        ctx.metrics["validation_passed"] = False
        ctx.metrics["validation_decision"] = ValidationDecision.REJECT.value
        ctx.metrics["rollback_applied"] = True
        ctx.metrics["rollback_reason"] = primary_reason
        ctx.metrics["rollback_violations"] = [v.to_dict() for v in result.violations]
        ctx.metrics["compression_applied"] = False
        ctx.metrics["tokens_saved"] = 0
        ctx.metrics["optimized_token_count"] = ctx.original_token_count
        ctx.metrics["validation_invariants_checked"] = result.checked_invariants_count
        ctx.metrics["validation_invariants_passed"] = result.passed_invariants_count
        ctx.metrics["validation_invariants_failed"] = result.failed_invariants_count

    def _record_accept(self, ctx: OptimizationContext, result: ValidationResult) -> None:
        """Record successful validation telemetry on context metrics."""
        ctx.metrics["validation_passed"] = True
        ctx.metrics["validation_decision"] = ValidationDecision.ACCEPT.value
        ctx.metrics["rollback_applied"] = False
        ctx.metrics["validation_invariants_checked"] = result.checked_invariants_count
        ctx.metrics["validation_invariants_passed"] = result.passed_invariants_count
        ctx.metrics["validation_invariants_failed"] = 0

    def _handle_validator_exception(self, ctx: OptimizationContext, exc: Exception) -> None:
        """Handle unhandled validator exceptions with strict fail-closed rollback."""
        ctx.messages = deepcopy(ctx.original_messages)

        attempted_tokens = ctx.metrics.get("tokens_saved", 0)
        if attempted_tokens > 0:
            ctx.metrics["attempted_tokens_saved"] = attempted_tokens

        ctx.metrics["validation_passed"] = False
        ctx.metrics["validation_decision"] = ValidationDecision.REJECT.value
        ctx.metrics["rollback_applied"] = True
        ctx.metrics["rollback_reason"] = f"validator_exception: {exc}"
        ctx.metrics["validator_error"] = str(exc)
        ctx.metrics["compression_applied"] = False
        ctx.metrics["tokens_saved"] = 0
        ctx.metrics["optimized_token_count"] = ctx.original_token_count


def count_message_tokens_safe(messages: list[dict[str, Any]], model: str) -> int:
    """Safe token count helper that avoids importing from non-production code."""
    from tokenopt.utils.token_counter import count_message_tokens
    return count_message_tokens(messages, model)
