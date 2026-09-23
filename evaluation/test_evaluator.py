"""Self-tests for the deterministic compression-fidelity evaluation harness.

Verifies:
1. Role-aware preservation: markers surviving only in the wrong message/role fail.
2. Structural safety checks: syntax errors in code, JSON, and markdown tables are caught.
3. Valid content passes all checks cleanly.
4. Non-structured cases return syntax_valid = None.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.cases import ExpectedMarker
from evaluation.runner import (
    check_markers,
    check_structural_syntax,
    validate_json_syntax,
    validate_markdown_table_structure,
    validate_python_syntax,
)


def test_marker_in_correct_role_and_index_passes() -> None:
    """A marker present in its expected message index and role passes."""
    expected = [ExpectedMarker(message_index=0, role="user", marker="CRITICAL_TOKEN")]
    messages = [{"role": "user", "content": "Here is the CRITICAL_TOKEN in place."}]

    preserved, missing, role_passed, marker_passed, failures = check_markers(
        expected, messages
    )

    assert marker_passed is True, "Expected marker preservation to pass"
    assert role_passed is True, "Expected role preservation to pass"
    assert len(preserved) == 1
    assert len(missing) == 0
    assert failures == []


def test_marker_surviving_in_wrong_message_fails() -> None:
    """A marker missing from its expected message but surviving in another message fails."""
    expected = [ExpectedMarker(message_index=0, role="user", marker="SECRET_KEY")]
    # Message 0 lost the marker; message 1 (assistant) contains it.
    messages = [
        {"role": "user", "content": "Can you check my configuration?"},
        {"role": "assistant", "content": "I noticed you referenced SECRET_KEY earlier."},
    ]

    preserved, missing, role_passed, marker_passed, failures = check_markers(
        expected, messages
    )

    assert marker_passed is False, "Marker in wrong message must fail marker preservation"
    assert role_passed is False, "Marker in wrong message must fail role preservation"
    assert len(missing) == 1
    assert "role_mismatch" in failures
    assert "missing_required_marker" in failures


def test_role_mismatch_fails() -> None:
    """A message whose role differs from the expectation fails role preservation."""
    expected = [ExpectedMarker(message_index=0, role="system", marker="STRICT_RULE")]
    # Message 0 has the marker, but role is 'user' instead of 'system'.
    messages = [{"role": "user", "content": "STRICT_RULE: always reply in English."}]

    preserved, missing, role_passed, marker_passed, failures = check_markers(
        expected, messages
    )

    assert marker_passed is False, "Role mismatch must fail marker preservation"
    assert role_passed is False, "Role mismatch must fail role preservation"
    assert "role_mismatch" in failures


def test_completely_missing_marker_fails() -> None:
    """A marker that does not survive anywhere fails marker preservation."""
    expected = [ExpectedMarker(message_index=0, role="user", marker="DEAD_TOKEN")]
    messages = [{"role": "user", "content": "Everything was truncated."}]

    preserved, missing, role_passed, marker_passed, failures = check_markers(
        expected, messages
    )

    assert marker_passed is False
    assert role_passed is True  # Message role was intact; token was simply lost
    assert "missing_required_marker" in failures
    assert "role_mismatch" not in failures


def test_missing_message_index_fails() -> None:
    """An expected marker targeting a message index beyond the message count fails."""
    expected = [ExpectedMarker(message_index=3, role="user", marker="FUTURE_TOKEN")]
    messages = [{"role": "user", "content": "Only one message exists."}]

    preserved, missing, role_passed, marker_passed, failures = check_markers(
        expected, messages
    )

    assert marker_passed is False
    assert role_passed is False
    assert "missing_required_marker" in failures
    assert "role_mismatch" in failures


def test_python_syntax_validation() -> None:
    """ast.parse validates complete Python code and rejects truncated fragments."""
    valid_code = (
        "class PaymentGatewayClient:\n"
        "    MAX_RETRIES = 3\n"
        "    def process_payment(self, amount: float) -> bool:\n"
        "        if amount <= 0.0:\n"
        "            raise ValueError('Invalid amount')\n"
        "        return True\n"
    )
    truncated_code = (
        "class PaymentGatewayClient:\n"
        " MAX_RETRIES = 3\n"
        " def process_payment(self, amount: float) -> bool:\n"
        " if amount <="
    )

    assert validate_python_syntax(valid_code) is True
    assert validate_python_syntax(truncated_code) is False

    valid_res, valid_err = check_structural_syntax(
        "code", [{"role": "user", "content": valid_code}]
    )
    assert valid_res is True
    assert valid_err is None

    invalid_res, invalid_err = check_structural_syntax(
        "code", [{"role": "user", "content": truncated_code}]
    )
    assert invalid_res is False
    assert invalid_err == "python_syntax_invalid"


def test_json_syntax_validation() -> None:
    """json.loads validates well-formed JSON and rejects truncated objects."""
    valid_json = (
        '{\n  "cluster_id": "us-east-prod-77",\n  "node_count": 12,\n  "auto_scaling": true\n}'
    )
    truncated_json = '{\n "cluster_id": "us-east-prod-77",\n "node_count": 12,\n "'

    assert validate_json_syntax(valid_json) is True
    assert validate_json_syntax(truncated_json) is False

    valid_res, valid_err = check_structural_syntax(
        "json", [{"role": "user", "content": valid_json}]
    )
    assert valid_res is True
    assert valid_err is None

    invalid_res, invalid_err = check_structural_syntax(
        "json", [{"role": "user", "content": truncated_json}]
    )
    assert invalid_res is False
    assert invalid_err == "json_invalid"


def test_markdown_table_validation() -> None:
    """Markdown table validator requires consistent columns and properly terminated rows."""
    valid_table = (
        "| Region | Tier | SLA Target | Status |\n"
        "|:---|:---:|:---:|:---|\n"
        "| US-East | Tier-1 | 99.99% | Compliant |\n"
        "| EU-Central | Tier-2 | 99.90% | Breach |\n"
    )
    unterminated_table = (
        "| Region | Tier | SLA Target | Status |\n"
        "|:---|:---:|:---:|:---|\n"
        "| US-East | Tier-1 | 99.99% | Compliant |\n"
        "| EU"
    )
    inconsistent_cols = (
        "| Region | Tier | SLA Target | Status |\n"
        "|:---|:---:|:---:|:---|\n"
        "| US-East | Tier-1 | 99.99% |\n"
    )

    assert validate_markdown_table_structure(valid_table) is True
    assert validate_markdown_table_structure(unterminated_table) is False
    assert validate_markdown_table_structure(inconsistent_cols) is False

    valid_res, valid_err = check_structural_syntax(
        "markdown_table", [{"role": "user", "content": valid_table}]
    )
    assert valid_res is True
    assert valid_err is None

    invalid_res, invalid_err = check_structural_syntax(
        "markdown_table", [{"role": "user", "content": unterminated_table}]
    )
    assert invalid_res is False
    assert invalid_err == "markdown_structure_invalid"


def test_non_structured_categories_return_none() -> None:
    """Categories without structural safety checks return syntax_valid = None."""
    non_structured = [
        "simple_conversation",
        "instruction_heavy",
        "system_user",
        "numeric_constraints",
        "date_constraints",
        "rag_context",
        "repetitive_context",
        "truncation_risk",
        "minimal_compression",
    ]
    messages = [{"role": "user", "content": "Just arbitrary prompt text."}]
    for category in non_structured:
        syntax_valid, failure_code = check_structural_syntax(category, messages)
        assert syntax_valid is None, f"Expected None for category {category}"
        assert failure_code is None, f"Expected None failure code for {category}"


def run_all_tests() -> None:
    """Run all self-test functions deterministically."""
    tests = [
        test_marker_in_correct_role_and_index_passes,
        test_marker_surviving_in_wrong_message_fails,
        test_role_mismatch_fails,
        test_completely_missing_marker_fails,
        test_missing_message_index_fails,
        test_python_syntax_validation,
        test_json_syntax_validation,
        test_markdown_table_validation,
        test_non_structured_categories_return_none,
    ]

    print("Running evaluation harness self-tests:")
    passed = 0
    for test in tests:
        test()
        print(f"  [PASS] {test.__name__}")
        passed += 1

    print(f"\nAll {passed} self-tests passed successfully.")


if __name__ == "__main__":
    run_all_tests()
