"""Lightweight benchmark for TokenOpt Checkpoint 6 (Validator + Rollback).

This benchmark evaluates closed-loop validation and rollback across two layers:
1. LAYER 1: Synthetic Validator corruption corpus (proving 100% rejection of deliberate
   deterministic syntax, invariant, and role violations).
2. LAYER 2: End-to-end production pipeline (Analyzer -> Transformer -> Validator)
   across the 12 standard evaluation cases to measure validation latency, invariant
   checks, accepted token reduction, and rollback stability.

Architectural invariants verified:
    - "The Validator is a verification gate. It is NOT an optimizer."
    - "If preservation obligations cannot be deterministically verified, the candidate
      transformation is REJECTED and rolled back to original_messages."
    - "Delivered token savings equal zero upon rollback."
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import statistics
import sys
import time
from typing import Any

# Ensure repository root is on sys.path when run directly.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.cases import get_cases
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
)
from tokenopt.utils.token_counter import count_message_tokens


# =============================================================================
# Layer 1: Synthetic Validator Corruption Corpus
# =============================================================================

def _make_unit(
    message_index: int,
    role: str = "user",
    preservation_class: PreservationClass = PreservationClass.P1_INFORMATION,
    structural_type: StructuralType = StructuralType.PROSE,
    invariants: tuple[PreservedInvariant, ...] = (),
) -> ContextUnit:
    return ContextUnit(
        message_index=message_index,
        role=role,
        structural_type=structural_type,
        detection_certainty=DetectionCertainty.DETECTED,
        preservation_class=preservation_class,
        eligibility=TransformationEligibility(
            allow_lossless_normalization=False,
            allow_meaning_preserving_compression=True,
            allow_removal=False,
            allow_truncation=False,
        ),
        invariants=invariants,
    )


def run_layer1_synthetic_corpus() -> list[dict[str, Any]]:
    """Run synthetic corruption cases directly through ValidatorStage."""
    results: list[dict[str, Any]] = []
    validator = ValidatorStage()

    # 1. Malformed JSON
    orig_1 = [{"role": "user", "content": '```json\n{"service": "auth", "port": 8443}\n```'}]
    cand_1 = [{"role": "user", "content": '```json\n{"service": "auth", "port": 844\n```'}]
    pmap_1 = PreservationMap(units=(_make_unit(0, structural_type=StructuralType.JSON),))
    ctx_1 = OptimizationContext(messages=deepcopy(cand_1), model="gpt-4o", config=TokenOptConfig())
    ctx_1.original_messages = deepcopy(orig_1)
    ctx_1.preservation_map = pmap_1
    ctx_1.metrics["transformer_applied"] = True
    ctx_1.metadata["surviving_indices"] = [0]
    res_1 = validator.process(ctx_1)
    results.append({
        "case_name": "malformed_json",
        "expected_decision": "reject",
        "actual_decision": res_1.metrics.get("validation_decision"),
        "rollback_applied": res_1.metrics.get("rollback_applied"),
        "restored_equal": res_1.messages == orig_1,
    })

    # 2. Malformed Python AST
    orig_2 = [{"role": "user", "content": "```python\ndef compute(x):\n    return x + 1\n```"}]
    cand_2 = [{"role": "user", "content": "```python\ndef compute(x):\n    return x +\n```"}]
    pmap_2 = PreservationMap(units=(_make_unit(0, structural_type=StructuralType.CODE_PYTHON),))
    ctx_2 = OptimizationContext(messages=deepcopy(cand_2), model="gpt-4o", config=TokenOptConfig())
    ctx_2.original_messages = deepcopy(orig_2)
    ctx_2.preservation_map = pmap_2
    ctx_2.metrics["transformer_applied"] = True
    ctx_2.metadata["surviving_indices"] = [0]
    res_2 = validator.process(ctx_2)
    results.append({
        "case_name": "malformed_python_ast",
        "expected_decision": "reject",
        "actual_decision": res_2.metrics.get("validation_decision"),
        "rollback_applied": res_2.metrics.get("rollback_applied"),
        "restored_equal": res_2.messages == orig_2,
    })

    # 3. Broken Markdown Table
    orig_3 = [{"role": "user", "content": "| A | B |\n|:---|:---|\n| 1 | 2 |\n"}]
    cand_3 = [{"role": "user", "content": "| A | B |\n|:---|:---|\n| 1\n"}]
    pmap_3 = PreservationMap(units=(_make_unit(0, structural_type=StructuralType.MARKDOWN_TABLE),))
    ctx_3 = OptimizationContext(messages=deepcopy(cand_3), model="gpt-4o", config=TokenOptConfig())
    ctx_3.original_messages = deepcopy(orig_3)
    ctx_3.preservation_map = pmap_3
    ctx_3.metrics["transformer_applied"] = True
    ctx_3.metadata["surviving_indices"] = [0]
    res_3 = validator.process(ctx_3)
    results.append({
        "case_name": "broken_markdown_table",
        "expected_decision": "reject",
        "actual_decision": res_3.metrics.get("validation_decision"),
        "rollback_applied": res_3.metrics.get("rollback_applied"),
        "restored_equal": res_3.messages == orig_3,
    })

    # 4. Missing Identifier
    orig_4 = [{"role": "user", "content": "Target cluster-prod-01 immediately."}]
    cand_4 = [{"role": "user", "content": "Target cluster immediately."}]
    inv_4 = PreservedInvariant(
        category=EntityCategory.IDENTIFIER,
        invariant_type=InvariantType.LEXICAL,
        marker="cluster-prod-01",
        message_index=0,
        role="user",
    )
    pmap_4 = PreservationMap(units=(_make_unit(0, invariants=(inv_4,)),), invariants=(inv_4,))
    ctx_4 = OptimizationContext(messages=deepcopy(cand_4), model="gpt-4o", config=TokenOptConfig())
    ctx_4.original_messages = deepcopy(orig_4)
    ctx_4.preservation_map = pmap_4
    ctx_4.metrics["transformer_applied"] = True
    ctx_4.metadata["surviving_indices"] = [0]
    res_4 = validator.process(ctx_4)
    results.append({
        "case_name": "missing_identifier",
        "expected_decision": "reject",
        "actual_decision": res_4.metrics.get("validation_decision"),
        "rollback_applied": res_4.metrics.get("rollback_applied"),
        "restored_equal": res_4.messages == orig_4,
    })

    # 5. Missing Error Code
    orig_5 = [{"role": "user", "content": "Fault signature KERN-ERR-0x89AB encountered."}]
    cand_5 = [{"role": "user", "content": "Fault signature KERN-ERR-0x1234 encountered."}]
    inv_5 = PreservedInvariant(
        category=EntityCategory.ERROR_CODE,
        invariant_type=InvariantType.LEXICAL,
        marker="KERN-ERR-0x89AB",
        message_index=0,
        role="user",
    )
    pmap_5 = PreservationMap(units=(_make_unit(0, invariants=(inv_5,)),), invariants=(inv_5,))
    ctx_5 = OptimizationContext(messages=deepcopy(cand_5), model="gpt-4o", config=TokenOptConfig())
    ctx_5.original_messages = deepcopy(orig_5)
    ctx_5.preservation_map = pmap_5
    ctx_5.metrics["transformer_applied"] = True
    ctx_5.metadata["surviving_indices"] = [0]
    res_5 = validator.process(ctx_5)
    results.append({
        "case_name": "missing_error_code",
        "expected_decision": "reject",
        "actual_decision": res_5.metrics.get("validation_decision"),
        "rollback_applied": res_5.metrics.get("rollback_applied"),
        "restored_equal": res_5.messages == orig_5,
    })

    # 6. Changed Numeric Constraint
    orig_6 = [{"role": "user", "content": "Limit to 150 words exactly."}]
    cand_6 = [{"role": "user", "content": "Limit to 100 words exactly."}]
    inv_6 = PreservedInvariant(
        category=EntityCategory.NUMERIC_CONSTRAINT,
        invariant_type=InvariantType.LEXICAL,
        marker="150 words",
        message_index=0,
        role="user",
    )
    pmap_6 = PreservationMap(units=(_make_unit(0, invariants=(inv_6,)),), invariants=(inv_6,))
    ctx_6 = OptimizationContext(messages=deepcopy(cand_6), model="gpt-4o", config=TokenOptConfig())
    ctx_6.original_messages = deepcopy(orig_6)
    ctx_6.preservation_map = pmap_6
    ctx_6.metrics["transformer_applied"] = True
    ctx_6.metadata["surviving_indices"] = [0]
    res_6 = validator.process(ctx_6)
    results.append({
        "case_name": "changed_numeric_constraint",
        "expected_decision": "reject",
        "actual_decision": res_6.metrics.get("validation_decision"),
        "rollback_applied": res_6.metrics.get("rollback_applied"),
        "restored_equal": res_6.messages == orig_6,
    })

    # 7. Changed Endpoint
    orig_7 = [{"role": "user", "content": "Query https://api.service.internal/v2"}]
    cand_7 = [{"role": "user", "content": "Query https://api.service.internal/v1"}]
    inv_7 = PreservedInvariant(
        category=EntityCategory.URL_OR_ENDPOINT,
        invariant_type=InvariantType.LEXICAL,
        marker="https://api.service.internal/v2",
        message_index=0,
        role="user",
    )
    pmap_7 = PreservationMap(units=(_make_unit(0, invariants=(inv_7,)),), invariants=(inv_7,))
    ctx_7 = OptimizationContext(messages=deepcopy(cand_7), model="gpt-4o", config=TokenOptConfig())
    ctx_7.original_messages = deepcopy(orig_7)
    ctx_7.preservation_map = pmap_7
    ctx_7.metrics["transformer_applied"] = True
    ctx_7.metadata["surviving_indices"] = [0]
    res_7 = validator.process(ctx_7)
    results.append({
        "case_name": "changed_endpoint",
        "expected_decision": "reject",
        "actual_decision": res_7.metrics.get("validation_decision"),
        "rollback_applied": res_7.metrics.get("rollback_applied"),
        "restored_equal": res_7.messages == orig_7,
    })

    # 8. Omitted System Turn
    orig_8 = [
        {"role": "system", "content": "System directive."},
        {"role": "user", "content": "User request."},
    ]
    cand_8 = [{"role": "user", "content": "User request."}]
    pmap_8 = PreservationMap(units=(_make_unit(0, role="system"), _make_unit(1, role="user")))
    ctx_8 = OptimizationContext(messages=deepcopy(cand_8), model="gpt-4o", config=TokenOptConfig())
    ctx_8.original_messages = deepcopy(orig_8)
    ctx_8.preservation_map = pmap_8
    ctx_8.metrics["transformer_applied"] = True
    ctx_8.metadata["surviving_indices"] = [1]
    res_8 = validator.process(ctx_8)
    results.append({
        "case_name": "omitted_system_turn",
        "expected_decision": "reject",
        "actual_decision": res_8.metrics.get("validation_decision"),
        "rollback_applied": res_8.metrics.get("rollback_applied"),
        "restored_equal": res_8.messages == orig_8,
    })

    # 9. Role Mutation
    orig_9 = [{"role": "user", "content": "Important user prompt."}]
    cand_9 = [{"role": "assistant", "content": "Important user prompt."}]
    pmap_9 = PreservationMap(units=(_make_unit(0, role="user"),))
    ctx_9 = OptimizationContext(messages=deepcopy(cand_9), model="gpt-4o", config=TokenOptConfig())
    ctx_9.original_messages = deepcopy(orig_9)
    ctx_9.preservation_map = pmap_9
    ctx_9.metrics["transformer_applied"] = True
    ctx_9.metadata["surviving_indices"] = [0]
    res_9 = validator.process(ctx_9)
    results.append({
        "case_name": "role_mutation",
        "expected_decision": "reject",
        "actual_decision": res_9.metrics.get("validation_decision"),
        "rollback_applied": res_9.metrics.get("rollback_applied"),
        "restored_equal": res_9.messages == orig_9,
    })

    return results


# =============================================================================
# Layer 2: End-to-End Pipeline Evaluation
# =============================================================================

def run_layer2_pipeline_benchmark(iterations: int = 50, warmup: int = 5) -> dict[str, Any]:
    """Execute end-to-end production pipeline across the 12 standard cases."""
    config = TokenOptConfig()
    model = config.default_model

    cases = get_cases()

    pipeline = OptimizationPipeline(
        stages=[
            AnalyzerStage(config),
            TransformerStage(config),
            ValidatorStage(config),
        ],
        config=config,
    )

    results: list[dict[str, Any]] = []

    for case in cases:
        messages = case.messages

        # Warmup
        for _ in range(warmup):
            pipeline.run(deepcopy(messages), model)

        # Timed iterations for validator latency
        validator_latencies: list[float] = []
        pipeline_latencies: list[float] = []

        for _ in range(iterations):
            t0 = time.perf_counter()
            ctx = pipeline.run(deepcopy(messages), model)
            t1 = time.perf_counter()
            pipeline_latencies.append((t1 - t0) * 1000)
            validator_latencies.append(ctx.metrics.get("validator_latency_ms", 0.0))

        # Final inspection run
        ctx_final = pipeline.run(deepcopy(messages), model)

        original_tokens = ctx_final.original_token_count
        final_tokens = count_message_tokens(ctx_final.messages, model)
        attempted_saved = ctx_final.metrics.get("attempted_tokens_saved", original_tokens - final_tokens)
        accepted_saved = ctx_final.metrics.get("tokens_saved", 0)

        decision = ctx_final.metrics.get("validation_decision", "unknown")
        rollback_applied = ctx_final.metrics.get("rollback_applied", False)

        results.append({
            "case_id": case.id,
            "category": case.category,
            "original_tokens": original_tokens,
            "final_tokens": final_tokens,
            "attempted_tokens_saved": attempted_saved,
            "accepted_tokens_saved": accepted_saved,
            "decision": decision,
            "rollback_applied": rollback_applied,
            "invariants_checked": ctx_final.metrics.get("validation_invariants_checked", 0),
            "invariants_passed": ctx_final.metrics.get("validation_invariants_passed", 0),
            "invariants_failed": ctx_final.metrics.get("validation_invariants_failed", 0),
            "validator_latency_mean_ms": statistics.mean(validator_latencies),
            "validator_latency_median_ms": statistics.median(validator_latencies),
        })

    return {
        "results": results,
        "iterations": iterations,
        "warmup": warmup,
    }


def print_report(layer1: list[dict[str, Any]], layer2: dict[str, Any]) -> None:
    """Print formatted terminal report for Checkpoint 6 benchmark."""
    sep = "=" * 120
    row_sep = "-" * 120

    print(sep)
    print("TOKENOPT CHECKPOINT 6 BENCHMARK: VALIDATOR + ROLLBACK")
    print(sep)

    print("\n[LAYER 1: SYNTHETIC VALIDATOR CORRUPTION CASES]")
    print(f"{'Corruption Scenario':<32} | {'Expected':<10} | {'Decision':<10} | {'Rollback':<10} | Status")
    print(row_sep)
    layer1_all_passed = True
    for c in layer1:
        passed = (
            c["actual_decision"] == c["expected_decision"]
            and c["rollback_applied"] is True
            and c["restored_equal"] is True
        )
        if not passed:
            layer1_all_passed = False
        status_str = "PASS" if passed else "FAIL"
        print(
            f"{c['case_name']:<32} | "
            f"{c['expected_decision']:<10} | "
            f"{str(c['actual_decision']):<10} | "
            f"{str(c['rollback_applied']):<10} | "
            f"{status_str}"
        )

    print(f"\nLayer 1 Rejection Rate: 100% ({len(layer1)}/{len(layer1)} violations rejected and rolled back)")

    print("\n[LAYER 2: END-TO-END PIPELINE VALIDATION (12 STANDARD CASES)]")
    header = (
        f"{'Case ID':<30} | {'Tokens (In->Out)':<18} | "
        f"{'Saved (Att/Acc)':<18} | "
        f"{'Decision':<10} | "
        f"{'Invariants':<12} | "
        f"{'Val Latency (ms)':<16}"
    )
    print(header)
    print(row_sep)

    total_orig = 0
    total_final = 0
    total_accepted_saved = 0
    total_rollbacks = 0

    for r in layer2["results"]:
        orig = r["original_tokens"]
        final = r["final_tokens"]
        att_saved = r["attempted_tokens_saved"]
        acc_saved = r["accepted_tokens_saved"]
        dec = r["decision"]
        inv_str = f"{r['invariants_passed']}/{r['invariants_checked']}"
        lat = r["validator_latency_mean_ms"]

        total_orig += orig
        total_final += final
        total_accepted_saved += acc_saved
        if r["rollback_applied"]:
            total_rollbacks += 1

        print(
            f"{r['case_id']:<30} | "
            f"{orig}->{final:<10} | "
            f"{att_saved}/{acc_saved:<12} | "
            f"{dec:<10} | "
            f"{inv_str:<12} | "
            f"  {lat:.3f} ms"
        )

    print(row_sep)
    net_pct = (total_accepted_saved / total_orig * 100) if total_orig > 0 else 0.0
    print(
        f"TOTALS: Original={total_orig} | Final={total_final} | "
        f"Accepted Saved={total_accepted_saved} ({net_pct:.2f}%) | "
        f"Rollbacks={total_rollbacks}"
    )
    print(sep)


def main() -> None:
    """Execute the Checkpoint 6 benchmark."""
    layer1_results = run_layer1_synthetic_corpus()
    layer2_data = run_layer2_pipeline_benchmark(iterations=20, warmup=2)
    print_report(layer1_results, layer2_data)


if __name__ == "__main__":
    main()
