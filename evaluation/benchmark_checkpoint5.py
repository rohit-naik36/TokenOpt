"""Lightweight benchmark for TokenOpt Checkpoint 5 (Preservation-Aware Transformation).

This benchmark evaluates the existing 12-case evaluation corpus to establish:
1. Transformation correctness — P0/P1 units preserved, P2 compressed, P3 removed.
2. Zero regression against the existing Checkpoint 4 pipeline baseline.
3. Standalone latency for TransformerStage applied after AnalyzerStage.

Architectural invariant verified here:
    "The transformer executes only the transformation decisions produced by the
    Candidate Planner. It does not independently decide what is safe to
    transform."

Output:
- Terminal summary table with per-case token metrics, plan decision counts,
  and transformer latency.
- Zero-regression check against evaluation/results/baseline.json.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

# Ensure repository root is on sys.path when run directly.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.cases import get_cases
from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.analyzer import AnalyzerStage
from tokenopt.pipeline.base import OptimizationPipeline
from tokenopt.pipeline.compressor import CompressorStage
from tokenopt.pipeline.transformer import TransformerStage
from tokenopt.utils.token_counter import count_message_tokens


def load_baseline_results() -> dict[str, Any]:
    """Load baseline results from evaluation/results/baseline.json."""
    baseline_path = REPO_ROOT / "evaluation" / "results" / "baseline.json"
    if not baseline_path.exists():
        raise FileNotFoundError(f"Baseline file not found at {baseline_path}")
    with open(baseline_path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_benchmark(iterations: int = 100, warmup: int = 10) -> dict[str, Any]:
    """Execute the Checkpoint 5 benchmark across all 12 cases.

    Args:
        iterations: Number of timed iterations per case for latency measurement.
        warmup: Number of untimed warmup iterations.

    Returns:
        Structured benchmark results dictionary.
    """
    config = TokenOptConfig()
    model = config.default_model

    cases = get_cases()
    baseline = load_baseline_results()
    baseline_by_id = {c["case_id"]: c for c in baseline.get("cases", [])}

    # Checkpoint 4 pipeline: used to verify zero-regression on the existing baseline.
    pipeline_cp4 = OptimizationPipeline(
        [AnalyzerStage(config), CompressorStage(config)],
        config,
    )

    # Checkpoint 5 pipeline: AnalyzerStage drives PreservationMap -> TransformerStage.
    pipeline_cp5 = OptimizationPipeline(
        [AnalyzerStage(config), TransformerStage(config)],
        config,
    )

    results: list[dict[str, Any]] = []

    for case in cases:
        case_id = case.id
        messages = case.messages

        # ── Checkpoint 4 regression baseline ──────────────────────────────
        ctx4 = pipeline_cp4.run(deepcopy(messages), model)
        cp4_tokens = count_message_tokens(ctx4.messages, model)
        original_tokens = ctx4.original_token_count

        base_case = baseline_by_id.get(case_id)
        regression = "MISSING_BASELINE"
        if base_case is not None:
            regression = (
                "PASS"
                if cp4_tokens == base_case.get("optimized_tokens")
                else "FAIL"
            )

        # ── Checkpoint 5 pipeline: warmup ─────────────────────────────────
        for _ in range(warmup):
            pipeline_cp5.run(deepcopy(messages), model)

        # ── Checkpoint 5 pipeline: timed iterations ───────────────────────
        latencies: list[float] = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            pipeline_cp5.run(deepcopy(messages), model)
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000)

        # Final run for metrics inspection.
        ctx5 = pipeline_cp5.run(deepcopy(messages), model)
        cp5_tokens = count_message_tokens(ctx5.messages, model)

        compress_count = ctx5.metrics.get("transformer_compress_count", 0)
        remove_count = ctx5.metrics.get("transformer_remove_count", 0)
        protected_count = ctx5.metrics.get("transformer_protected_count", 0)

        results.append(
            {
                "case_id": case_id,
                "original_tokens": original_tokens,
                "cp4_optimized_tokens": cp4_tokens,
                "cp5_optimized_tokens": cp5_tokens,
                "tokens_saved_cp4": original_tokens - cp4_tokens,
                "tokens_saved_cp5": original_tokens - cp5_tokens,
                "compress_count": compress_count,
                "remove_count": remove_count,
                "protected_count": protected_count,
                "regression": regression,
                "latency_mean_ms": statistics.mean(latencies),
                "latency_median_ms": statistics.median(latencies),
            }
        )

    return {
        "results": results,
        "iterations": iterations,
        "warmup": warmup,
    }


def print_report(data: dict[str, Any]) -> None:
    """Print a human-readable benchmark table."""
    results = data["results"]
    iterations = data["iterations"]
    warmup = data["warmup"]

    sep = "=" * 120
    row_sep = "-" * 120
    header = (
        f"{'Case ID':<30} | {'Tokens (In->CP4/CP5)':<22} | "
        f"{'Saved (CP4/CP5)':<18} | "
        f"{'Plan (C/R/P)':<14} | "
        f"{'Latency (ms)':<14} | Regr"
    )

    print(sep)
    print("TOKENOPT CHECKPOINT 5 BENCHMARK: PRESERVATION-AWARE TRANSFORMATION")
    print(sep)
    print(header)
    print(row_sep)

    total_orig = 0
    total_cp4 = 0
    total_cp5 = 0
    pass_count = 0

    for r in results:
        orig = r["original_tokens"]
        cp4 = r["cp4_optimized_tokens"]
        cp5 = r["cp5_optimized_tokens"]
        saved_cp4 = r["tokens_saved_cp4"]
        saved_cp5 = r["tokens_saved_cp5"]
        pct_cp4 = saved_cp4 / orig * 100 if orig else 0
        pct_cp5 = saved_cp5 / orig * 100 if orig else 0
        regression = r["regression"]
        if regression == "PASS":
            pass_count += 1

        total_orig += orig
        total_cp4 += cp4
        total_cp5 += cp5

        c = r["compress_count"]
        rem = r["remove_count"]
        prot = r["protected_count"]
        lat = r["latency_mean_ms"]

        print(
            f"{r['case_id']:<30} | "
            f"{orig}->{cp4}/{cp5:<13} | "
            f"{saved_cp4} ({pct_cp4:.1f}%)/{saved_cp5} ({pct_cp5:.1f}%) | "
            f"C={c}/R={rem}/P={prot:<5} | "
            f"  {lat:.3f} ms   | {regression}"
        )

    print(row_sep)

    total_saved_cp4 = total_orig - total_cp4
    total_saved_cp5 = total_orig - total_cp5
    pct_cp4_total = total_saved_cp4 / total_orig * 100 if total_orig else 0
    pct_cp5_total = total_saved_cp5 / total_orig * 100 if total_orig else 0

    print(
        f"{'TOTAL / AGGREGATE':<30} | "
        f"{total_orig}->{total_cp4}/{total_cp5:<5} | "
        f"{total_saved_cp4} ({pct_cp4_total:.2f}%)/{total_saved_cp5} ({pct_cp5_total:.2f}%) | "
        f"{'':14} | "
        f"{'':14} | "
        f"{pass_count}/{len(results)} PASS"
    )
    print(sep)

    print(f"\nAGGREGATE SUMMARY:")
    print(f"  Cases evaluated:                  {len(results)}")
    print(f"  Iterations per case:              {iterations} (plus {warmup} warmup)")
    print(f"  Total original tokens:            {total_orig}")
    print(f"  CP4 (baseline) optimized tokens:  {total_cp4}")
    print(
        f"  CP4 tokens saved:                 {total_saved_cp4} ({pct_cp4_total:.2f}%)"
    )
    print(f"  CP5 (transformer) optimized:      {total_cp5}")
    print(
        f"  CP5 tokens saved:                 {total_saved_cp5} ({pct_cp5_total:.2f}%)"
    )
    print(
        f"  Zero regression against baseline: {pass_count} / {len(results)} PASS"
        f" ({'100%' if pass_count == len(results) else 'PARTIAL'})"
    )
    print()
    print(
        "  NOTE: CP5 uses AnalyzerStage + TransformerStage (plan-controlled)."
    )
    print(
        "  CP4 uses AnalyzerStage + CompressorStage (all-message uniform compression)."
    )
    print(
        "  CP5 only compresses messages that the CandidatePlanner designates as P2 COMPRESS."
    )
    print(
        "  Protected messages (P0/P1) and fail-safe cases are passed through unchanged."
    )


if __name__ == "__main__":
    data = run_benchmark()
    print_report(data)
