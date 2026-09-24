"""Tests for ValidatorStage (Checkpoint 6: Closed-Loop Validation & Rollback).

Architectural invariant verified:
    "The Validator is a verification gate. It does NOT independently decide
    transformation eligibility, optimize content, or alter Planner authority.
    If preservation cannot be deterministically established, the candidate
    transformation is REJECTED and rolled back to original_messages."

Test inventory (covering Scenarios A through Z):
A. Valid unchanged/protected context passes.
B. Valid compression passes when required invariants survive.
C. Missing P1 identifier -> reject + rollback.
D. Changed error code -> reject + rollback.
E. Changed URL -> reject + rollback.
F. Changed numeric constraint -> reject + rollback.
G. Missing negative constraint -> reject + rollback.
H. Invalid JSON -> reject + rollback.
I. Invalid Python -> reject + rollback.
J. Broken Markdown table -> reject + rollback.
K. System message removal -> reject + rollback.
L. Role mutation -> reject + rollback.
M. Message removal causes index shift but valid surviving invariant still passes.
N. Multiple removals map correctly.
O. First message removal maps correctly.
P. Middle message removal maps correctly.
Q. Last message removal maps correctly.
R. All removable messages removed triggers turn non-destruction rejection.
S. Missing surviving_indices -> fail closed.
T. Malformed surviving_indices -> fail closed.
U. Validator exception -> fail-closed rollback.
V. Rollback restores exact original messages.
W. Rollback resets delivered token savings to zero.
X. Planner authority remains unchanged (Validator does not modify plan).
Y. Validator does not mutate candidate message content.
Z. Pipeline integration verifies Validator is positioned immediately after Transformer.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from unittest.mock import patch

from tokenopt.clients.openai_client import OpenAI
from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.analyzer import AnalyzerStage
from tokenopt.pipeline.base import OptimizationContext, OptimizationPipeline
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
from tokenopt.pipeline.transformer import TransformerStage
from tokenopt.pipeline.validator import (
    ValidationDecision,
    ValidatorStage,
    validate_json_syntax,
    validate_markdown_table_structure,
    validate_python_syntax,
    validate_tool_payload,
)

MODEL = "gpt-4o"


def _make_config(**kwargs: Any) -> TokenOptConfig:
    return TokenOptConfig(**kwargs)


def _make_ctx(
    messages: list[dict[str, Any]],
    preservation_map: PreservationMap | None = None,
    config: TokenOptConfig | None = None,
    surviving_indices: list[int] | None = None,
    transformer_applied: bool = True,
) -> OptimizationContext:
    cfg = config or _make_config()
    ctx = OptimizationContext(
        messages=deepcopy(messages),
        model=MODEL,
        config=cfg,
    )
    ctx.preservation_map = preservation_map
    if transformer_applied:
        ctx.metrics["transformer_applied"] = True
    if surviving_indices is not None:
        ctx.metadata["surviving_indices"] = list(surviving_indices)
    else:
        ctx.metadata["surviving_indices"] = list(range(len(messages)))
    return ctx


def _make_eligibility(
    *,
    allow_compression: bool = False,
    allow_removal: bool = False,
) -> TransformationEligibility:
    return TransformationEligibility(
        allow_lossless_normalization=False,
        allow_meaning_preserving_compression=allow_compression,
        allow_removal=allow_removal,
        allow_truncation=False,
    )


def _make_unit(
    message_index: int,
    role: str = "user",
    preservation_class: PreservationClass = PreservationClass.P1_INFORMATION,
    structural_type: StructuralType = StructuralType.PROSE,
    invariants: tuple[PreservedInvariant, ...] = (),
    eligibility: TransformationEligibility | None = None,
) -> ContextUnit:
    return ContextUnit(
        message_index=message_index,
        role=role,
        structural_type=structural_type,
        detection_certainty=DetectionCertainty.DETECTED,
        preservation_class=preservation_class,
        eligibility=eligibility or _make_eligibility(),
        invariants=invariants,
    )


# =============================================================================
# Structural Syntax Unit Tests
# =============================================================================

class TestStructuralSyntaxParsers:
    def test_python_syntax_valid(self) -> None:
        valid_code = "```python\ndef add(a: int, b: int) -> int:\n    return a + b\n```"
        assert validate_python_syntax(valid_code) is True

    def test_python_syntax_invalid(self) -> None:
        invalid_code = "```python\ndef add(a: int, b: int) -> int:\n    return a +\n```"
        assert validate_python_syntax(invalid_code) is False

    def test_python_syntax_bare_code(self) -> None:
        bare_code = "def foo():\n    return 42"
        assert validate_python_syntax(bare_code) is True

    def test_json_syntax_valid(self) -> None:
        valid_json = '{"name": "service-auth", "port": 8443, "active": true}'
        assert validate_json_syntax(valid_json) is True

    def test_json_syntax_fenced(self) -> None:
        fenced_json = '```json\n{"cluster_id": "prod-01", "nodes": 5}\n```'
        assert validate_json_syntax(fenced_json) is True

    def test_json_syntax_invalid(self) -> None:
        invalid_json = '{"name": "service-auth", "port": 8443'
        assert validate_json_syntax(invalid_json) is False

    def test_markdown_table_valid(self) -> None:
        valid_table = (
            "| Service | Port | Status |\n"
            "|:---|:---|:---|\n"
            "| auth | 8443 | active |\n"
            "| db | 5432 | ready |\n"
        )
        assert validate_markdown_table_structure(valid_table) is True

    def test_markdown_table_invalid_unterminated(self) -> None:
        invalid_table = (
            "| Service | Port | Status |\n"
            "|:---|:---|:---|\n"
            "| auth | 8443\n"
        )
        assert validate_markdown_table_structure(invalid_table) is False

    def test_markdown_table_invalid_separator(self) -> None:
        invalid_table = (
            "| Service | Port |\n"
            "| abc | def |\n"
            "| auth | 8443 |\n"
        )
        assert validate_markdown_table_structure(invalid_table) is False

    def test_tool_payload_validation(self) -> None:
        assert validate_tool_payload({"key": "val"}) is True
        assert validate_tool_payload('{"key": "val"}') is True
        assert validate_tool_payload('{"key": ') is False


# =============================================================================
# Scenarios A through Z
# =============================================================================

class TestValidatorStageScenarios:
    # A. Valid unchanged/protected context passes.
    def test_scenario_a_valid_unchanged_passes(self) -> None:
        msgs = [{"role": "system", "content": "You are a helpful assistant."}]
        inv = PreservedInvariant(
            category=EntityCategory.SECURITY_COMPLIANCE,
            invariant_type=InvariantType.LEXICAL,
            marker="helpful assistant",
            message_index=0,
            role="system",
        )
        unit = _make_unit(
            0,
            role="system",
            preservation_class=PreservationClass.P0_AUTHORITY,
            invariants=(inv,),
        )
        pmap = PreservationMap(units=(unit,), invariants=(inv,))
        ctx = _make_ctx(msgs, preservation_map=pmap)

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        assert result_ctx.metrics["validation_passed"] is True
        assert result_ctx.metrics["validation_decision"] == ValidationDecision.ACCEPT.value
        assert result_ctx.metrics["rollback_applied"] is False

    # B. Valid compression passes when required invariants survive.
    def test_scenario_b_valid_compression_passes(self) -> None:
        orig_msgs = [
            {
                "role": "user",
                "content": "Please could you deploy project Apollo to staging.",
            }
        ]
        cand_msgs = [{"role": "user", "content": "Deploy project Apollo to staging."}]
        inv = PreservedInvariant(
            category=EntityCategory.IDENTIFIER,
            invariant_type=InvariantType.LEXICAL,
            marker="project Apollo",
            message_index=0,
            role="user",
        )
        unit = _make_unit(
            0,
            role="user",
            preservation_class=PreservationClass.P2_COMPRESSIBLE,
            invariants=(inv,),
        )
        pmap = PreservationMap(units=(unit,), invariants=(inv,))

        ctx = _make_ctx(orig_msgs, preservation_map=pmap)
        ctx.messages = cand_msgs  # candidate transformed
        ctx.metrics["compression_applied"] = True
        ctx.metrics["tokens_saved"] = 4

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        assert result_ctx.metrics["validation_passed"] is True
        assert result_ctx.metrics["rollback_applied"] is False
        assert result_ctx.messages[0]["content"] == "Deploy project Apollo to staging."

    # C. Missing P1 identifier -> reject + rollback.
    def test_scenario_c_missing_p1_identifier_rejects_and_rolls_back(self) -> None:
        orig_msgs = [{"role": "user", "content": "Query cluster-prod-01 for health status."}]
        cand_msgs = [{"role": "user", "content": "Query cluster for health status."}]
        inv = PreservedInvariant(
            category=EntityCategory.IDENTIFIER,
            invariant_type=InvariantType.LEXICAL,
            marker="cluster-prod-01",
            message_index=0,
            role="user",
        )
        unit = _make_unit(0, invariants=(inv,))
        pmap = PreservationMap(units=(unit,), invariants=(inv,))

        ctx = _make_ctx(orig_msgs, preservation_map=pmap)
        ctx.messages = cand_msgs
        ctx.metrics["tokens_saved"] = 5

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        assert result_ctx.metrics["validation_passed"] is False
        assert result_ctx.metrics["validation_decision"] == ValidationDecision.REJECT.value
        assert result_ctx.metrics["rollback_applied"] is True
        assert result_ctx.metrics["tokens_saved"] == 0
        assert result_ctx.messages == orig_msgs

    # D. Changed error code -> reject + rollback.
    def test_scenario_d_changed_error_code_rejects(self) -> None:
        orig_msgs = [{"role": "user", "content": "Encountered KERN-ERR-0x89AB in module auth."}]
        cand_msgs = [{"role": "user", "content": "Encountered KERN-ERR-0x1234 in module auth."}]
        inv = PreservedInvariant(
            category=EntityCategory.ERROR_CODE,
            invariant_type=InvariantType.LEXICAL,
            marker="KERN-ERR-0x89AB",
            message_index=0,
            role="user",
        )
        unit = _make_unit(0, invariants=(inv,))
        pmap = PreservationMap(units=(unit,), invariants=(inv,))

        ctx = _make_ctx(orig_msgs, preservation_map=pmap)
        ctx.messages = cand_msgs

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        assert result_ctx.metrics["rollback_applied"] is True
        assert result_ctx.messages == orig_msgs

    # E. Changed URL -> reject + rollback.
    def test_scenario_e_changed_url_rejects(self) -> None:
        orig_msgs = [{"role": "user", "content": "Connect to https://api.prod.service/v2"}]
        cand_msgs = [{"role": "user", "content": "Connect to https://api.prod.service/v1"}]
        inv = PreservedInvariant(
            category=EntityCategory.URL_OR_ENDPOINT,
            invariant_type=InvariantType.LEXICAL,
            marker="https://api.prod.service/v2",
            message_index=0,
            role="user",
        )
        unit = _make_unit(0, invariants=(inv,))
        pmap = PreservationMap(units=(unit,), invariants=(inv,))

        ctx = _make_ctx(orig_msgs, preservation_map=pmap)
        ctx.messages = cand_msgs

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        assert result_ctx.metrics["rollback_applied"] is True
        assert result_ctx.messages == orig_msgs

    # F. Changed numeric constraint -> reject + rollback.
    def test_scenario_f_changed_numeric_constraint_rejects(self) -> None:
        orig_msgs = [{"role": "user", "content": "Limit response to 150 words."}]
        cand_msgs = [{"role": "user", "content": "Limit response to 100 words."}]
        inv = PreservedInvariant(
            category=EntityCategory.NUMERIC_CONSTRAINT,
            invariant_type=InvariantType.LEXICAL,
            marker="150 words",
            message_index=0,
            role="user",
        )
        unit = _make_unit(0, invariants=(inv,))
        pmap = PreservationMap(units=(unit,), invariants=(inv,))

        ctx = _make_ctx(orig_msgs, preservation_map=pmap)
        ctx.messages = cand_msgs

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        assert result_ctx.metrics["rollback_applied"] is True
        assert result_ctx.messages == orig_msgs

    # G. Missing negative constraint -> reject + rollback.
    def test_scenario_g_missing_negative_constraint_rejects(self) -> None:
        orig_msgs = [
            {
                "role": "system",
                "content": "Do not disclose private keys under any circumstances.",
            }
        ]
        cand_msgs = [
            {
                "role": "system",
                "content": "Disclose private keys under any circumstances.",
            }
        ]
        inv = PreservedInvariant(
            category=EntityCategory.NEGATIVE_CONSTRAINT,
            invariant_type=InvariantType.LEXICAL,
            marker="Do not disclose",
            message_index=0,
            role="system",
        )
        unit = _make_unit(
            0,
            role="system",
            preservation_class=PreservationClass.P0_AUTHORITY,
            invariants=(inv,),
        )
        pmap = PreservationMap(units=(unit,), invariants=(inv,))

        ctx = _make_ctx(orig_msgs, preservation_map=pmap)
        ctx.messages = cand_msgs

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        assert result_ctx.metrics["rollback_applied"] is True
        assert result_ctx.messages == orig_msgs

    # H. Invalid JSON -> reject + rollback.
    def test_scenario_h_invalid_json_rejects(self) -> None:
        orig_msgs = [{"role": "user", "content": '```json\n{"service": "auth", "port": 8443}\n```'}]
        cand_msgs = [{"role": "user", "content": '```json\n{"service": "auth", "port": 844\n```'}]
        unit = _make_unit(0, structural_type=StructuralType.JSON)
        pmap = PreservationMap(units=(unit,))

        ctx = _make_ctx(orig_msgs, preservation_map=pmap)
        ctx.messages = cand_msgs

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        assert result_ctx.metrics["rollback_applied"] is True
        assert result_ctx.messages == orig_msgs
        assert "json_syntax" in str(result_ctx.metrics["rollback_violations"])

    # I. Invalid Python -> reject + rollback.
    def test_scenario_i_invalid_python_rejects(self) -> None:
        orig_msgs = [
            {"role": "user", "content": "```python\ndef compute(val):\n    return val * 2\n```"}
        ]
        cand_msgs = [
            {"role": "user", "content": "```python\ndef compute(val):\n    return val *\n```"}
        ]
        unit = _make_unit(0, structural_type=StructuralType.CODE_PYTHON)
        pmap = PreservationMap(units=(unit,))

        ctx = _make_ctx(orig_msgs, preservation_map=pmap)
        ctx.messages = cand_msgs

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        assert result_ctx.metrics["rollback_applied"] is True
        assert result_ctx.messages == orig_msgs
        assert "python_code_syntax" in str(result_ctx.metrics["rollback_violations"])

    # J. Broken Markdown table -> reject + rollback.
    def test_scenario_j_broken_markdown_table_rejects(self) -> None:
        orig_msgs = [
            {
                "role": "user",
                "content": "| Col1 | Col2 |\n|:---|:---|\n| A | B |\n",
            }
        ]
        cand_msgs = [
            {
                "role": "user",
                "content": "| Col1 | Col2 |\n|:---|:---|\n| A\n",
            }
        ]
        unit = _make_unit(0, structural_type=StructuralType.MARKDOWN_TABLE)
        pmap = PreservationMap(units=(unit,))

        ctx = _make_ctx(orig_msgs, preservation_map=pmap)
        ctx.messages = cand_msgs

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        assert result_ctx.metrics["rollback_applied"] is True
        assert result_ctx.messages == orig_msgs

    # K. System message removal -> reject + rollback.
    def test_scenario_k_system_message_removal_rejects(self) -> None:
        orig_msgs = [
            {"role": "system", "content": "System prompt."},
            {"role": "user", "content": "User prompt."},
        ]
        cand_msgs = [{"role": "user", "content": "User prompt."}]
        pmap = PreservationMap(units=(_make_unit(0, role="system"), _make_unit(1, role="user")))

        ctx = _make_ctx(orig_msgs, preservation_map=pmap, surviving_indices=[1])
        ctx.messages = cand_msgs

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        assert result_ctx.metrics["rollback_applied"] is True
        assert result_ctx.messages == orig_msgs
        assert "system_message_protection" in result_ctx.metrics["rollback_reason"]

    # L. Role mutation -> reject + rollback.
    def test_scenario_l_role_mutation_rejects(self) -> None:
        orig_msgs = [{"role": "user", "content": "User prompt."}]
        cand_msgs = [{"role": "assistant", "content": "User prompt."}]
        pmap = PreservationMap(units=(_make_unit(0, role="user"),))

        ctx = _make_ctx(orig_msgs, preservation_map=pmap, surviving_indices=[0])
        ctx.messages = cand_msgs

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        assert result_ctx.metrics["rollback_applied"] is True
        assert result_ctx.messages == orig_msgs
        assert "role_integrity" in result_ctx.metrics["rollback_reason"]

    # M. Message removal causes index shift but valid surviving invariant still passes.
    def test_scenario_m_index_shift_with_surviving_invariant_passes(self) -> None:
        orig_msgs = [
            {"role": "user", "content": "Hello, how are you doing today?"},
            {"role": "user", "content": "Deploy cluster-prod-01 to staging."},
        ]
        cand_msgs = [{"role": "user", "content": "Deploy cluster-prod-01 to staging."}]
        inv = PreservedInvariant(
            category=EntityCategory.IDENTIFIER,
            invariant_type=InvariantType.LEXICAL,
            marker="cluster-prod-01",
            message_index=1,
            role="user",
        )
        unit0 = _make_unit(0, preservation_class=PreservationClass.P3_REMOVABLE)
        unit1 = _make_unit(
            1,
            preservation_class=PreservationClass.P1_INFORMATION,
            invariants=(inv,),
        )
        pmap = PreservationMap(units=(unit0, unit1), invariants=(inv,))

        ctx = _make_ctx(orig_msgs, preservation_map=pmap, surviving_indices=[1])
        ctx.messages = cand_msgs

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        assert result_ctx.metrics["validation_passed"] is True
        assert result_ctx.metrics["rollback_applied"] is False

    # N. Multiple removals map correctly.
    def test_scenario_n_multiple_removals_map_correctly(self) -> None:
        orig_msgs = [
            {"role": "user", "content": "Hi there."},              # 0 (removed)
            {"role": "user", "content": "Keep cluster-prod-01."},   # 1 -> out 0
            {"role": "user", "content": "Thanks a lot."},           # 2 (removed)
            {"role": "user", "content": "Keep cluster-prod-02."},   # 3 -> out 1
        ]
        cand_msgs = [
            {"role": "user", "content": "Keep cluster-prod-01."},
            {"role": "user", "content": "Keep cluster-prod-02."},
        ]
        inv1 = PreservedInvariant(
            category=EntityCategory.IDENTIFIER,
            invariant_type=InvariantType.LEXICAL,
            marker="cluster-prod-01",
            message_index=1,
            role="user",
        )
        inv3 = PreservedInvariant(
            category=EntityCategory.IDENTIFIER,
            invariant_type=InvariantType.LEXICAL,
            marker="cluster-prod-02",
            message_index=3,
            role="user",
        )
        pmap = PreservationMap(
            units=(
                _make_unit(0, preservation_class=PreservationClass.P3_REMOVABLE),
                _make_unit(1, invariants=(inv1,)),
                _make_unit(2, preservation_class=PreservationClass.P3_REMOVABLE),
                _make_unit(3, invariants=(inv3,)),
            ),
            invariants=(inv1, inv3),
        )

        ctx = _make_ctx(orig_msgs, preservation_map=pmap, surviving_indices=[1, 3])
        ctx.messages = cand_msgs

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        assert result_ctx.metrics["validation_passed"] is True
        assert result_ctx.metrics["rollback_applied"] is False

    # O. First message removal maps correctly.
    def test_scenario_o_first_message_removal_maps_correctly(self) -> None:
        orig_msgs = [
            {"role": "user", "content": "Just saying hello."},
            {"role": "user", "content": "Target endpoint /v2/orders."},
        ]
        cand_msgs = [{"role": "user", "content": "Target endpoint /v2/orders."}]
        inv = PreservedInvariant(
            category=EntityCategory.URL_OR_ENDPOINT,
            invariant_type=InvariantType.LEXICAL,
            marker="/v2/orders",
            message_index=1,
            role="user",
        )
        unit0 = _make_unit(0, preservation_class=PreservationClass.P3_REMOVABLE)
        unit1 = _make_unit(1, invariants=(inv,))
        pmap = PreservationMap(
            units=(unit0, unit1),
            invariants=(inv,),
        )

        ctx = _make_ctx(orig_msgs, preservation_map=pmap, surviving_indices=[1])
        ctx.messages = cand_msgs

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        assert result_ctx.metrics["validation_passed"] is True
        assert result_ctx.metrics["rollback_applied"] is False

    # P. Middle message removal maps correctly.
    def test_scenario_p_middle_message_removal_maps_correctly(self) -> None:
        orig_msgs = [
            {"role": "user", "content": "First instruction token A."},
            {"role": "user", "content": "Polite filler."},
            {"role": "user", "content": "Third instruction token B."},
        ]
        cand_msgs = [
            {"role": "user", "content": "First instruction token A."},
            {"role": "user", "content": "Third instruction token B."},
        ]
        inv0 = PreservedInvariant(
            category=EntityCategory.IDENTIFIER,
            invariant_type=InvariantType.LEXICAL,
            marker="token A",
            message_index=0,
            role="user",
        )
        inv2 = PreservedInvariant(
            category=EntityCategory.IDENTIFIER,
            invariant_type=InvariantType.LEXICAL,
            marker="token B",
            message_index=2,
            role="user",
        )
        pmap = PreservationMap(
            units=(
                _make_unit(0, invariants=(inv0,)),
                _make_unit(1, preservation_class=PreservationClass.P3_REMOVABLE),
                _make_unit(2, invariants=(inv2,)),
            ),
            invariants=(inv0, inv2),
        )

        ctx = _make_ctx(orig_msgs, preservation_map=pmap, surviving_indices=[0, 2])
        ctx.messages = cand_msgs

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        assert result_ctx.metrics["validation_passed"] is True
        assert result_ctx.metrics["rollback_applied"] is False

    # Q. Last message removal maps correctly.
    def test_scenario_q_last_message_removal_maps_correctly(self) -> None:
        orig_msgs = [
            {"role": "user", "content": "Critical instruction token C."},
            {"role": "user", "content": "Thank you bye."},
        ]
        cand_msgs = [{"role": "user", "content": "Critical instruction token C."}]
        inv0 = PreservedInvariant(
            category=EntityCategory.IDENTIFIER,
            invariant_type=InvariantType.LEXICAL,
            marker="token C",
            message_index=0,
            role="user",
        )
        pmap = PreservationMap(
            units=(
                _make_unit(0, invariants=(inv0,)),
                _make_unit(1, preservation_class=PreservationClass.P3_REMOVABLE),
            ),
            invariants=(inv0,),
        )

        ctx = _make_ctx(orig_msgs, preservation_map=pmap, surviving_indices=[0])
        ctx.messages = cand_msgs

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        assert result_ctx.metrics["validation_passed"] is True
        assert result_ctx.metrics["rollback_applied"] is False

    # R. All removable messages removed triggers turn non-destruction rejection.
    def test_scenario_r_all_messages_removed_triggers_rejection(self) -> None:
        orig_msgs = [{"role": "user", "content": "Filler only."}]
        cand_msgs: list[dict[str, Any]] = []
        pmap = PreservationMap(
            units=(_make_unit(0, preservation_class=PreservationClass.P3_REMOVABLE),),
        )

        ctx = _make_ctx(orig_msgs, preservation_map=pmap, surviving_indices=[])
        ctx.messages = cand_msgs

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        assert result_ctx.metrics["rollback_applied"] is True
        assert result_ctx.messages == orig_msgs
        assert "turn_non_destruction" in result_ctx.metrics["rollback_reason"]

    # S. Missing surviving_indices -> fail closed.
    def test_scenario_s_missing_surviving_indices_fails_closed(self) -> None:
        orig_msgs = [{"role": "user", "content": "Some message."}]
        pmap = PreservationMap(units=(_make_unit(0),))
        ctx = _make_ctx(orig_msgs, preservation_map=pmap)
        del ctx.metadata["surviving_indices"]

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        assert result_ctx.metrics["rollback_applied"] is True
        assert result_ctx.metrics["validation_decision"] == ValidationDecision.REJECT.value
        assert "surviving_indices" in result_ctx.metrics["rollback_reason"]

    # T. Malformed surviving_indices -> fail closed.
    def test_scenario_t_malformed_surviving_indices_fails_closed(self) -> None:
        orig_msgs = [
            {"role": "user", "content": "Msg 0"},
            {"role": "user", "content": "Msg 1"},
        ]
        pmap = PreservationMap(units=(_make_unit(0), _make_unit(1)))
        # Non-monotonic or invalid indices: [1, 0]
        ctx = _make_ctx(orig_msgs, preservation_map=pmap, surviving_indices=[1, 0])

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        assert result_ctx.metrics["rollback_applied"] is True
        assert "surviving_indices" in result_ctx.metrics["rollback_reason"]

    # U. Validator exception -> fail-closed rollback.
    def test_scenario_u_validator_exception_rolls_back(self) -> None:
        orig_msgs = [{"role": "user", "content": "Some message."}]
        pmap = PreservationMap(units=(_make_unit(0),))
        ctx = _make_ctx(orig_msgs, preservation_map=pmap)

        stage = ValidatorStage()
        err = RuntimeError("Simulated validator crash")
        with patch.object(stage, "_validate", side_effect=err):
            result_ctx = stage.process(ctx)

        assert result_ctx.metrics["rollback_applied"] is True
        assert result_ctx.metrics["validation_decision"] == ValidationDecision.REJECT.value
        assert "validator_exception" in result_ctx.metrics["rollback_reason"]
        assert result_ctx.messages == orig_msgs

    # V. Rollback restores exact original messages.
    def test_scenario_v_rollback_restores_exact_original_messages(self) -> None:
        orig_msgs = [
            {"role": "system", "content": "System 1", "metadata": {"auth": True}},
            {"role": "user", "content": "User 1", "metadata": {"turn": 1}},
        ]
        corrupted_msgs = [
            {"role": "user", "content": "Corrupted content without system"},
        ]
        pmap = PreservationMap(units=(_make_unit(0, role="system"), _make_unit(1, role="user")))
        ctx = _make_ctx(orig_msgs, preservation_map=pmap, surviving_indices=[1])
        ctx.messages = corrupted_msgs

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        assert result_ctx.metrics["rollback_applied"] is True
        assert result_ctx.messages == orig_msgs
        assert result_ctx.messages[0]["role"] == "system"
        assert result_ctx.messages[0]["metadata"]["auth"] is True

    # W. Rollback resets delivered token savings to zero.
    def test_scenario_w_rollback_resets_token_savings_to_zero(self) -> None:
        orig_msgs = [{"role": "user", "content": "Required token-XYZ must survive."}]
        corrupted_msgs = [{"role": "user", "content": "Stripped token."}]
        inv = PreservedInvariant(
            category=EntityCategory.IDENTIFIER,
            invariant_type=InvariantType.LEXICAL,
            marker="token-XYZ",
            message_index=0,
            role="user",
        )
        pmap = PreservationMap(units=(_make_unit(0, invariants=(inv,)),), invariants=(inv,))

        ctx = _make_ctx(orig_msgs, preservation_map=pmap)
        ctx.messages = corrupted_msgs
        ctx.metrics["tokens_saved"] = 15
        ctx.metrics["optimized_token_count"] = 5

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        assert result_ctx.metrics["rollback_applied"] is True
        assert result_ctx.metrics["tokens_saved"] == 0
        assert result_ctx.metrics["optimized_token_count"] == ctx.original_token_count
        assert result_ctx.metrics["compression_applied"] is False

    # X. Planner authority remains unchanged (Validator does not modify plan).
    def test_scenario_x_planner_authority_remains_unchanged(self) -> None:
        orig_msgs = [{"role": "user", "content": "Please deploy project Apollo."}]
        unit = _make_unit(0, preservation_class=PreservationClass.P2_COMPRESSIBLE)
        pmap = PreservationMap(units=(unit,))
        ctx = _make_ctx(orig_msgs, preservation_map=pmap)

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        # Validator does not attach or modify CandidatePlan
        assert "candidate_plan" not in result_ctx.metadata
        assert result_ctx.preservation_map == pmap

    # Y. Validator does not transform content.
    def test_scenario_y_validator_does_not_transform_content(self) -> None:
        cand_msgs = [{"role": "user", "content": "Exact candidate content untouched."}]
        pmap = PreservationMap(units=(_make_unit(0),))
        ctx = _make_ctx(cand_msgs, preservation_map=pmap)
        ctx.messages = cand_msgs

        stage = ValidatorStage()
        result_ctx = stage.process(ctx)

        assert result_ctx.metrics["validation_passed"] is True
        assert result_ctx.messages[0]["content"] == "Exact candidate content untouched."

    # Z. Pipeline integration verifies Validator is positioned after Transformer.
    def test_scenario_z_pipeline_integration_positioning(self) -> None:
        client = OpenAI(api_key="test-key")
        stage_names = [s.name for s in client.pipeline.stages]
        assert "transformer" in stage_names
        assert "validator" in stage_names
        transformer_idx = stage_names.index("transformer")
        validator_idx = stage_names.index("validator")
        assert validator_idx == transformer_idx + 1
        summarizer_idx = stage_names.index("summarizer")
        assert summarizer_idx == validator_idx + 1


# =============================================================================
# End-to-End Pipeline Integration Tests
# =============================================================================

class TestEndToEndPipelineWithValidator:
    def test_end_to_end_accepted_transformation(self) -> None:
        cfg = TokenOptConfig()
        pipeline = OptimizationPipeline(
            stages=[
                AnalyzerStage(cfg),
                TransformerStage(cfg),
                ValidatorStage(cfg),
            ],
            config=cfg,
        )
        messages = [
            {
                "role": "user",
                "content": "Hello! Could you please help me understand project Apollo?",
            }
        ]
        ctx = pipeline.run(messages, model=MODEL)

        assert ctx.metrics.get("validation_passed") is True
        assert ctx.metrics.get("validation_decision") == ValidationDecision.ACCEPT.value
        assert ctx.metrics.get("rollback_applied") is False
        assert "project Apollo" in ctx.messages[0]["content"]

    def test_end_to_end_corrupted_transformation_triggers_rollback(self) -> None:
        cfg = TokenOptConfig()

        class CorruptingTransformer(TransformerStage):
            def process(self, ctx: OptimizationContext) -> OptimizationContext:
                ctx = super().process(ctx)
                # Intentionally corrupt the output by stripping an invariant
                ctx.messages = [{"role": "user", "content": "Corrupted text with missing marker."}]
                return ctx

        pipeline = OptimizationPipeline(
            stages=[
                AnalyzerStage(cfg),
                CorruptingTransformer(cfg),
                ValidatorStage(cfg),
            ],
            config=cfg,
        )
        messages = [
            {"role": "user", "content": "Deploy cluster-prod-01 to staging now."}
        ]
        ctx = pipeline.run(messages, model=MODEL)

        assert ctx.metrics.get("validation_passed") is False
        assert ctx.metrics.get("validation_decision") == ValidationDecision.REJECT.value
        assert ctx.metrics.get("rollback_applied") is True
        assert ctx.messages == messages
        assert ctx.metrics.get("tokens_saved") == 0
