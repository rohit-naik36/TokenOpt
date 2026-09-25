"""Deterministic task-fidelity evaluators for TokenOpt evaluation cases."""

from __future__ import annotations

import re
from collections.abc import Callable

from tokenopt.evaluation.schema import TaskFidelityEvidence, TaskFidelityStatus


def _count_bullet_points(text: str) -> int:
    """Count bullet points or numbered list items in text."""
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^(?:[-*•]|\d+[.)])\s+", stripped):
            count += 1
    return count


def _evaluate_case_02(text: str) -> tuple[bool, str]:
    """Assert case_02 directives: [EXEC-SUMMARY], Level-4, and 3 bullet points."""
    details: list[str] = []
    has_exec_summary = "[EXEC-SUMMARY]" in text or "[exec-summary]" in text.lower()
    if not has_exec_summary:
        details.append("missing [EXEC-SUMMARY]")

    has_level_4 = "level-4" in text.lower()
    if not has_level_4:
        details.append("missing Level-4")

    bullet_count = _count_bullet_points(text)
    has_3_bullets = bullet_count == 3
    if not has_3_bullets:
        details.append(f"expected 3 bullet points, found {bullet_count}")

    passed = has_exec_summary and has_level_4 and has_3_bullets
    msg = "All case_02 directives verified" if passed else "; ".join(details)
    return passed, msg


_CASE_05_DATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b2026-01-15\b", re.IGNORECASE),
    re.compile(r"\b(?:January|Jan)\.?\s+15(?:th)?,?\s+2026\b", re.IGNORECASE),
    re.compile(r"\b15(?:th)?\s+(?:of\s+)?(?:January|Jan)\.?,?\s+2026\b", re.IGNORECASE),
)


def _evaluate_case_05(text: str) -> tuple[bool, str]:
    """Assert case_05 contractual date: '2026-01-15' (or equivalent) and 'Phase-2'."""
    has_date = any(p.search(text) for p in _CASE_05_DATE_PATTERNS)
    has_phase = bool(re.search(r"phase[\s-]2\b", text, re.IGNORECASE))
    passed = has_date and has_phase
    if passed:
        return True, "Found binding date (2026-01-15 or equivalent) and Phase-2"
    missing = []
    if not has_date:
        missing.append("missing 2026-01-15 or equivalent date (e.g. January 15, 2026)")
    if not has_phase:
        missing.append("missing Phase-2")
    return False, "; ".join(missing)


def _evaluate_case_07(text: str) -> tuple[bool, str]:
    """Assert case_07 JSON query: extracted node_count == '12'."""
    has_12 = bool(re.search(r"\b12\b", text))
    if has_12:
        return True, "Extracted node_count value 12"
    return False, "Missing expected node_count 12"


def _evaluate_case_08(text: str) -> tuple[bool, str]:
    """Assert case_08 table query: identified EU-Central as SLA breach."""
    text_lower = text.lower()
    identifies_eu = "eu-central" in text_lower or "eu central" in text_lower
    # Ensure it doesn't falsely blame US-East or AP-South
    falsely_blames_us = bool(re.search(r"us-east\b[^\n.!?]*\bbreach\b", text_lower))
    falsely_blames_ap = bool(re.search(r"ap-south\b[^\n.!?]*\bbreach\b", text_lower))

    if identifies_eu and not falsely_blames_us and not falsely_blames_ap:
        return True, "Correctly identified EU-Central as SLA breach"
    reasons = []
    if not identifies_eu:
        reasons.append("did not identify EU-Central as breach")
    if falsely_blames_us:
        reasons.append("falsely claimed US-East breached")
    if falsely_blames_ap:
        reasons.append("falsely claimed AP-South breached")
    return False, "; ".join(reasons)


def _evaluate_case_09(text: str) -> tuple[bool, str]:
    """Assert case_09 RAG query: notification within 15 minutes, Sev-1 / security-ops."""
    text_lower = text.lower()
    has_time = bool(re.search(r"\b15[\s-]*(?:minutes?|mins?)\b", text_lower))
    has_target = bool(
        "security-ops@acme.corp" in text_lower or "sev-1" in text_lower or "sev 1" in text_lower
    )
    if has_time and has_target:
        return True, "Found 15-minute timeframe and Sev-1 / security-ops target"
    missing = []
    if not has_time:
        missing.append("missing 15 minutes timeframe")
    if not has_target:
        missing.append("missing Sev-1 or security-ops@acme.corp")
    return False, "; ".join(missing)


def _evaluate_case_11(text: str) -> tuple[bool, str]:
    """Assert case_11 log query: detected fatal panic, Node-99, or KERN-ERR-0x89AB."""
    text_lower = text.lower()
    has_node = "node-99" in text_lower
    has_err = "kern-err-0x89ab" in text_lower or "0x89ab" in text_lower
    has_panic = "fatal panic" in text_lower or "panic" in text_lower

    if has_node or has_err or has_panic:
        return True, "Detected terminal alert (Node-99 / KERN-ERR-0x89AB / panic)"
    return False, "Failed to identify terminal critical alert from log tail"


_CASE_EVALUATORS: dict[str, tuple[str, Callable[[str], tuple[bool, str]]]] = {
    "case_02_instruction_heavy": ("assert_executive_report_directives", _evaluate_case_02),
    "case_05_date_constraints": ("assert_contractual_date_phase", _evaluate_case_05),
    "case_07_json": ("assert_node_count_extracted", _evaluate_case_07),
    "case_08_markdown_table": ("assert_eu_central_sla_breach", _evaluate_case_08),
    "case_09_rag_context": ("assert_incident_response_requirements", _evaluate_case_09),
    "case_11_truncation_risk": ("assert_fatal_panic_alert_detected", _evaluate_case_11),
}


def evaluate_task_fidelity(
    case_id: str,
    baseline_completion: str,
    tokenopt_completion: str,
) -> TaskFidelityEvidence:
    """Evaluate deterministic task assertions on generated completions.

    Returns TaskFidelityEvidence with status PASSED, FAILED, or NOT_EVALUATED.
    """
    if case_id not in _CASE_EVALUATORS:
        return TaskFidelityEvidence(
            status=TaskFidelityStatus.NOT_EVALUATED,
            assertion_name=None,
            baseline_passed=None,
            tokenopt_passed=None,
            details="No deterministic task assertion applicable for open-ended response",
        )

    assertion_name, evaluator = _CASE_EVALUATORS[case_id]
    b_pass, b_msg = evaluator(baseline_completion)
    t_pass, t_msg = evaluator(tokenopt_completion)

    status = TaskFidelityStatus.PASSED if t_pass else TaskFidelityStatus.FAILED
    details = f"Baseline: {b_msg} | TokenOpt: {t_msg}"

    return TaskFidelityEvidence(
        status=status,
        assertion_name=assertion_name,
        baseline_passed=b_pass,
        tokenopt_passed=t_pass,
        details=details,
    )
