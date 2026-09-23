"""Deterministic compression-fidelity evaluation runner for TokenOpt.

This runner benchmarks the deterministic CompressorStage across the 12
standard evaluation cases to measure:
1. Token reduction metrics.
2. Role-aware preservation of critical information markers.
3. Structural safety checks for structured content (code, JSON, markdown tables).
4. Deterministic behavior across repeated runs.

Output:
- Terminal summary table and aggregate metrics.
- Machine-readable JSON report under evaluation/results/baseline.json.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure repository root is on sys.path so tokenopt and evaluation can be imported.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.cases import EvaluationCase, ExpectedMarker, get_cases
from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.base import OptimizationContext
from tokenopt.pipeline.compressor import CompressorStage
from tokenopt.utils.token_counter import count_message_tokens


def check_markers(
    expected_markers: list[ExpectedMarker],
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool, bool, list[str]]:
    """Check whether expected markers exist in the designated message role and index.

    A marker that survives in a DIFFERENT message or with a DIFFERENT role does
    NOT count as preserved, failing both marker and role preservation.

    Args:
        expected_markers: List of ExpectedMarker instances specifying (message_index, role, marker).
        messages: List of message dictionaries with 'role' and 'content'.

    Returns:
        tuple of:
        - preserved_markers: list of preserved marker dicts
        - missing_markers: list of missing marker dicts
        - role_preservation_passed: bool
        - marker_preservation_passed: bool
        - failure_reasons: list of failure reason codes
    """
    preserved: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    role_preservation_passed = True
    failure_reasons: list[str] = []

    for em in expected_markers:
        em_dict = em.to_dict()

        if em.message_index >= len(messages):
            # Message was dropped completely
            missing.append(em_dict)
            role_preservation_passed = False
            if "missing_required_marker" not in failure_reasons:
                failure_reasons.append("missing_required_marker")
            if "role_mismatch" not in failure_reasons:
                failure_reasons.append("role_mismatch")
            continue

        target_msg = messages[em.message_index]
        actual_role = target_msg.get("role")
        target_content = target_msg.get("content", "")
        if not isinstance(target_content, str):
            target_content = str(target_content)

        role_matches = (actual_role == em.role)
        marker_in_target = em.marker in target_content

        if role_matches and marker_in_target:
            preserved.append(em_dict)
        else:
            missing.append(em_dict)

            # Check if marker survived in a different message or wrong role
            survived_elsewhere = False
            for idx, msg in enumerate(messages):
                content = msg.get("content", "")
                if not isinstance(content, str):
                    content = str(content)
                if em.marker in content:
                    if idx != em.message_index or msg.get("role") != em.role:
                        survived_elsewhere = True
                        break

            if survived_elsewhere or not role_matches:
                role_preservation_passed = False
                if "role_mismatch" not in failure_reasons:
                    failure_reasons.append("role_mismatch")

            if "missing_required_marker" not in failure_reasons:
                failure_reasons.append("missing_required_marker")

    marker_preservation_passed = len(missing) == 0
    return (
        preserved,
        missing,
        role_preservation_passed,
        marker_preservation_passed,
        failure_reasons,
    )


def extract_python_code(text: str) -> str:
    """Extract Python code block from text, supporting fences or inline definitions."""
    fences = re.findall(r"```(?:python)?\s*\n(.*?)(?:```|$)", text, re.DOTALL)
    if fences:
        return fences[0]

    lines = text.splitlines()
    code_lines: list[str] = []
    in_code = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("class ", "def ", "import ", "from ")):
            in_code = True
        if in_code:
            # Prose following code block marks end of code snippet
            if stripped.startswith(("Could you", "Please", "What do", "Can you")):
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
    except SyntaxError:
        return False


def extract_json_payload(text: str) -> str | None:
    """Extract JSON object or array payload from text."""
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


def check_structural_syntax(
    case_category: str,
    messages: list[dict[str, Any]],
) -> tuple[bool | None, str | None]:
    """Check structural validity for structured categories.

    Returns:
        tuple of (syntax_valid, failure_code).
        syntax_valid is None for non-structured categories.
    """
    full_text = "\n\n".join(
        msg.get("content", "")
        for msg in messages
        if isinstance(msg.get("content"), str)
    )
    if case_category == "code":
        valid = validate_python_syntax(full_text)
        return valid, None if valid else "python_syntax_invalid"
    elif case_category == "json":
        valid = validate_json_syntax(full_text)
        return valid, None if valid else "json_invalid"
    elif case_category == "markdown_table":
        valid = validate_markdown_table_structure(full_text)
        return valid, None if valid else "markdown_structure_invalid"
    else:
        return None, None


def evaluate_case(
    case: EvaluationCase,
    stage: CompressorStage,
    config: TokenOptConfig,
) -> dict[str, Any]:
    """Evaluate a single test case against CompressorStage twice for determinism.

    Args:
        case: EvaluationCase instance.
        stage: CompressorStage instance.
        config: TokenOptConfig instance.

    Returns:
        Dictionary adhering to the evaluation result schema.
    """
    model = config.default_model

    # Run 1: Primary evaluation
    ctx1 = OptimizationContext(
        messages=deepcopy(case.messages),
        model=model,
        config=config,
    )
    original_tokens = ctx1.original_token_count
    ctx1 = stage.process(ctx1)
    optimized_messages_run1 = ctx1.messages
    optimized_tokens = count_message_tokens(optimized_messages_run1, model=model)

    tokens_saved = original_tokens - optimized_tokens
    reduction_pct = (
        round((tokens_saved / original_tokens) * 100.0, 2)
        if original_tokens > 0
        else 0.0
    )

    # Check role-aware fidelity markers
    (
        preserved_markers,
        missing_markers,
        role_preservation_passed,
        marker_preservation_passed,
        marker_failures,
    ) = check_markers(case.expected_preserved, optimized_messages_run1)

    # Check structural safety
    syntax_valid, syntax_failure = check_structural_syntax(
        case.category,
        optimized_messages_run1,
    )

    # Run 2: Determinism verification
    ctx2 = OptimizationContext(
        messages=deepcopy(case.messages),
        model=model,
        config=config,
    )
    ctx2 = stage.process(ctx2)
    optimized_messages_run2 = ctx2.messages

    deterministic_passed = (optimized_messages_run1 == optimized_messages_run2)

    # Compile failure reasons
    failure_reasons = list(marker_failures)
    if syntax_failure and syntax_failure not in failure_reasons:
        failure_reasons.append(syntax_failure)
    if not deterministic_passed and "nondeterministic_output" not in failure_reasons:
        failure_reasons.append("nondeterministic_output")

    # Overall fidelity determination
    fidelity_passed = (
        marker_preservation_passed
        and role_preservation_passed
        and (syntax_valid is None or syntax_valid is True)
        and deterministic_passed
    )

    return {
        "case_id": case.id,
        "id": case.id,
        "category": case.category,
        "description": case.description,
        "original_tokens": original_tokens,
        "optimized_tokens": optimized_tokens,
        "tokens_saved": tokens_saved,
        "reduction_pct": reduction_pct,
        "expected_markers_count": len(case.expected_preserved),
        "preserved_markers": preserved_markers,
        "missing_markers": missing_markers,
        "role_preservation_passed": role_preservation_passed,
        "marker_preservation_passed": marker_preservation_passed,
        "syntax_valid": syntax_valid,
        "deterministic_passed": deterministic_passed,
        "fidelity_passed": fidelity_passed,
        "failure_reasons": failure_reasons,
        "original_messages": case.messages,
        "optimized_messages": optimized_messages_run1,
    }


def run_evaluation(
    output_path: Path | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Execute the full evaluation harness and output results.

    Args:
        output_path: Path to write the JSON results. Defaults to evaluation/results/baseline.json.

    Returns:
        tuple of (aggregate_summary, case_results).
    """
    config = TokenOptConfig()
    stage = CompressorStage(config=config)
    cases = get_cases()

    case_results: list[dict[str, Any]] = []
    for case in cases:
        result = evaluate_case(case, stage, config)
        case_results.append(result)

    cases_total = len(case_results)
    fidelity_passed = sum(1 for r in case_results if r["fidelity_passed"])
    fidelity_failed = cases_total - fidelity_passed
    fidelity_pass_rate = round(
        (fidelity_passed / cases_total) * 100.0 if cases_total > 0 else 0.0,
        2,
    )

    deterministic_passed = sum(1 for r in case_results if r["deterministic_passed"])
    deterministic_failed = cases_total - deterministic_passed

    total_orig_tokens = sum(r["original_tokens"] for r in case_results)
    total_opt_tokens = sum(r["optimized_tokens"] for r in case_results)
    total_tokens_saved = total_orig_tokens - total_opt_tokens
    aggregate_reduction_pct = round(
        (total_tokens_saved / total_orig_tokens) * 100.0 if total_orig_tokens > 0 else 0.0,
        2,
    )

    aggregate = {
        "total_original_tokens": total_orig_tokens,
        "total_optimized_tokens": total_opt_tokens,
        "total_tokens_saved": total_tokens_saved,
        "aggregate_reduction_pct": aggregate_reduction_pct,
        "cases_total": cases_total,
        "fidelity_passed": fidelity_passed,
        "fidelity_failed": fidelity_failed,
        "fidelity_pass_rate": fidelity_pass_rate,
        "deterministic_passed": deterministic_passed,
        "deterministic_failed": deterministic_failed,
        # Backward compatibility aliases
        "total_cases": cases_total,
        "fidelity_passed_cases": fidelity_passed,
        "fidelity_failed_cases": fidelity_failed,
        "fidelity_pass_rate_pct": fidelity_pass_rate,
        "deterministic_passed_cases": deterministic_passed,
        "deterministic_failed_cases": deterministic_failed,
        "deterministic_pass_rate_pct": round(
            (deterministic_passed / cases_total) * 100.0 if cases_total > 0 else 0.0,
            2,
        ),
    }

    full_report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": stage.name,
        "model": config.default_model,
        "compression_ratio_config": config.compression_ratio,
        "aggregate": aggregate,
        "cases": case_results,
    }

    # Save to JSON
    if output_path is None:
        output_dir = REPO_ROOT / "evaluation" / "results"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "baseline.json"
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2)

    return aggregate, case_results


def print_summary(aggregate: dict[str, Any], case_results: list[dict[str, Any]]) -> None:
    """Print concise terminal summary."""
    print("=" * 96)
    print("TOKENOPT DETERMINISTIC COMPRESSOR EVALUATION HARNESS")
    print("=" * 96)
    print(f"Stage: CompressorStage (deterministic) | Cases: {aggregate['cases_total']}")
    print("-" * 96)
    header = (
        f"{'Case ID':<28} {'Category':<20} {'In -> Out':<11} {'Saved (%)':<11} "
        f"{'Syntax':<8} {'Fidelity':<10} {'Deterministic'}"
    )
    print(header)
    print("-" * 96)

    for r in case_results:
        syntax_str = "N/A" if r["syntax_valid"] is None else ("PASS" if r["syntax_valid"] else "FAIL")
        fid_str = "PASS" if r["fidelity_passed"] else "FAIL"
        det_str = "PASS" if r["deterministic_passed"] else "FAIL"
        tokens_str = f"{r['original_tokens']} -> {r['optimized_tokens']}"
        saved_str = f"{r['tokens_saved']} ({r['reduction_pct']}%)"
        print(
            f"{r['case_id']:<28} {r['category']:<20} {tokens_str:<11} {saved_str:<11} "
            f"{syntax_str:<8} {fid_str:<10} {det_str}"
        )

    print("-" * 96)
    print("AGGREGATE METRICS:")
    print(f"  total_original_tokens:   {aggregate['total_original_tokens']}")
    print(f"  total_optimized_tokens:  {aggregate['total_optimized_tokens']}")
    print(f"  total_tokens_saved:      {aggregate['total_tokens_saved']}")
    print(f"  aggregate_reduction_pct: {aggregate['aggregate_reduction_pct']}%")
    print(f"  cases_total:             {aggregate['cases_total']}")
    print(f"  fidelity_passed:         {aggregate['fidelity_passed']} / {aggregate['cases_total']}")
    print(f"  fidelity_failed:         {aggregate['fidelity_failed']} / {aggregate['cases_total']}")
    print(f"  fidelity_pass_rate:      {aggregate['fidelity_pass_rate']}%")
    print(f"  deterministic_passed:    {aggregate['deterministic_passed']} / {aggregate['cases_total']}")
    print(f"  deterministic_failed:    {aggregate['deterministic_failed']} / {aggregate['cases_total']}")

    failures = [r for r in case_results if not r["fidelity_passed"]]
    if failures:
        print("-" * 96)
        print("FAILURES & REASONS:")
        for f_case in failures:
            print(f"  [{f_case['case_id']}] ({f_case['category']}):")
            print(f"    Failure reasons:            {f_case['failure_reasons']}")
            print(f"    Role preservation:          {'PASS' if f_case['role_preservation_passed'] else 'FAIL'}")
            print(f"    Marker preservation:        {'PASS' if f_case['marker_preservation_passed'] else 'FAIL'}")
            print(f"    Syntax validity:            {f_case['syntax_valid']}")
            print(f"    Missing markers count:      {len(f_case['missing_markers'])}")

    print("=" * 96)
    results_file = REPO_ROOT / "evaluation" / "results" / "baseline.json"
    print(f"Full results written to: {results_file}")


def main() -> None:
    """CLI entrypoint."""
    aggregate, case_results = run_evaluation()
    print_summary(aggregate, case_results)


if __name__ == "__main__":
    main()
