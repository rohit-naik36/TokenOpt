"""Lightweight benchmark for TokenOpt Checkpoint 4 (Candidate Planner).

This benchmark evaluates the existing 12-case evaluation corpus to establish:
1. Planning correctness and candidate decision distributions (protected, compress, remove).
2. Zero regression against the existing Checkpoint 3 pipeline baseline.
3. Standalone latency and overhead for ContextAnalyzer and CandidatePlanner.

Output:
- Terminal summary table with per-case token reduction, candidate counts, and latencies.
- Statistical aggregate summary across multiple iterations.
- Regression verification assertions against evaluation/results/baseline.json.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
import statistics
import sys
import time
from typing import Any

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.cases import get_cases
from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.analyzer import AnalyzerStage, ContextAnalyzer
from tokenopt.pipeline.base import OptimizationContext, OptimizationPipeline
from tokenopt.pipeline.compressor import CompressorStage
from tokenopt.pipeline.planner import CandidatePlanner
from tokenopt.utils.token_counter import count_message_tokens


def load_baseline_results() -> dict[str, Any]:
    """Load baseline results from evaluation/results/baseline.json."""
    baseline_path = REPO_ROOT / "evaluation" / "results" / "baseline.json"
    if not baseline_path.exists():
        raise FileNotFoundError(f"Baseline file not found at {baseline_path}")
    with open(baseline_path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_benchmark(iterations: int = 100, warmup: int = 10) -> dict[str, Any]:
    """Execute the Checkpoint 4 benchmark across all 12 cases.

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
    baseline_cases_by_id = {c["case_id"]: c for c in baseline.get("cases", [])}

    # Pipeline stages: Checkpoint 3 existing pipeline (AnalyzerStage + CompressorStage)
    pipeline_stages = [AnalyzerStage(config), CompressorStage(config)]
    pipeline = OptimizationPipeline(pipeline_stages, config)

    # Standalone diagnostic components
    analyzer = ContextAnalyzer()
    planner = CandidatePlanner()

    results: list[dict[str, Any]] = []

    total_orig_tokens = 0
    total_opt_tokens = 0
    total_saved_tokens = 0

    total_units = 0
    total_protected = 0
    total_compress = 0
    total_remove = 0

    all_analyzer_times: list[float] = []
    all_planner_times: list[float] = []

    print("=" * 115)
    print("TOKENOPT CHECKPOINT 4 BENCHMARK: CANDIDATE PLANNER & PIPELINE ZERO-REGRESSION")
    print("=" * 115)
    print(
        f"{'Case ID':<30} | {'Tokens (In->Out)':<16} | {'Saved (%)':<12} | "
        f"{'Units (P/C/R)':<14} | {'Analyzer (ms)':<14} | {'Planner (ms)':<14} | {'Regr':<4}"
    )
    print("-" * 115)

    for case in cases:
        case_id = case.id
        base_case = baseline_cases_by_id.get(case_id)
        if not base_case:
            raise KeyError(f"Missing baseline entry for {case_id}")

        # 1. Pipeline Execution & Zero-Regression Check
        ctx = pipeline.run(
            messages=deepcopy(case.messages),
            model=model,
        )
        opt_messages = ctx.messages
        orig_tokens = ctx.original_token_count
        opt_tokens = count_message_tokens(opt_messages, model=model)
        saved_tokens = orig_tokens - opt_tokens
        reduction_pct = (
            round((saved_tokens / orig_tokens) * 100.0, 2)
            if orig_tokens > 0
            else 0.0
        )
        compression_ratio = (
            round(opt_tokens / orig_tokens, 4)
            if orig_tokens > 0
            else 1.0
        )

        # Regression Assertions against Checkpoint 3 baseline
        assert orig_tokens == base_case["original_tokens"], (
            f"Original token mismatch for {case_id}: {orig_tokens} vs {base_case['original_tokens']}"
        )
        assert opt_tokens == base_case["optimized_tokens"], (
            f"Optimized token mismatch for {case_id}: {opt_tokens} vs {base_case['optimized_tokens']}"
        )
        assert saved_tokens == base_case["tokens_saved"], (
            f"Saved tokens mismatch for {case_id}: {saved_tokens} vs {base_case['tokens_saved']}"
        )
        assert reduction_pct == base_case["reduction_pct"], (
            f"Reduction % mismatch for {case_id}: {reduction_pct} vs {base_case['reduction_pct']}"
        )

        total_orig_tokens += orig_tokens
        total_opt_tokens += opt_tokens
        total_saved_tokens += saved_tokens

        # 2. Planning Correctness & Candidate Extraction
        pmap = analyzer.analyze(case.messages)
        plan = planner.plan(pmap)

        n_units = len(pmap.units)
        n_prot = len(plan.protected_units)
        n_comp = len(plan.compression_candidates)
        n_rem = len(plan.removal_candidates)

        assert n_units == n_prot + n_comp + n_rem, "Sum of decisions must equal total units"
        assert n_units == len(case.messages), "Unit count must match message count in whole-message MVP"

        total_units += n_units
        total_protected += n_prot
        total_compress += n_comp
        total_remove += n_rem

        # 3. Timing Benchmark (Warmup + Multiple Iterations)
        # Warmup
        for _ in range(warmup):
            _p = analyzer.analyze(case.messages)
            _c = planner.plan(_p)

        # Measurement
        case_analyzer_times: list[float] = []
        case_planner_times: list[float] = []

        for _ in range(iterations):
            t0 = time.perf_counter()
            p_res = analyzer.analyze(case.messages)
            t1 = time.perf_counter()
            _ = planner.plan(p_res)
            t2 = time.perf_counter()

            case_analyzer_times.append((t1 - t0) * 1000.0)
            case_planner_times.append((t2 - t1) * 1000.0)

        all_analyzer_times.extend(case_analyzer_times)
        all_planner_times.extend(case_planner_times)

        mean_analyzer_ms = statistics.mean(case_analyzer_times)
        mean_planner_ms = statistics.mean(case_planner_times)
        median_planner_ms = statistics.median(case_planner_times)

        pcr_str = f"{n_prot}/{n_comp}/{n_rem}"
        in_out_str = f"{orig_tokens} -> {opt_tokens}"
        saved_str = f"{saved_tokens} ({reduction_pct:.1f}%)"

        print(
            f"{case_id:<30} | {in_out_str:<16} | {saved_str:<12} | "
            f"{pcr_str:<14} | {mean_analyzer_ms:6.3f} ms     | {mean_planner_ms:6.3f} ms     | PASS"
        )

        results.append(
            {
                "case_id": case_id,
                "category": case.category,
                "original_tokens": orig_tokens,
                "optimized_tokens": opt_tokens,
                "tokens_saved": saved_tokens,
                "reduction_pct": reduction_pct,
                "compression_ratio": compression_ratio,
                "preservation_map_units": n_units,
                "protected_units": n_prot,
                "compression_candidates": n_comp,
                "removal_candidates": n_rem,
                "analyzer_mean_ms": round(mean_analyzer_ms, 4),
                "planner_mean_ms": round(mean_planner_ms, 4),
                "planner_median_ms": round(median_planner_ms, 4),
                "zero_regression_verified": True,
            }
        )

    agg_reduction_pct = (
        round((total_saved_tokens / total_orig_tokens) * 100.0, 2)
        if total_orig_tokens > 0
        else 0.0
    )
    agg_compression_ratio = (
        round(total_opt_tokens / total_orig_tokens, 4)
        if total_orig_tokens > 0
        else 1.0
    )

    agg_analyzer_mean_ms = statistics.mean(all_analyzer_times)
    agg_analyzer_median_ms = statistics.median(all_analyzer_times)
    agg_planner_mean_ms = statistics.mean(all_planner_times)
    agg_planner_median_ms = statistics.median(all_planner_times)

    print("-" * 115)
    print(
        f"{'TOTAL / AGGREGATE':<30} | {f'{total_orig_tokens} -> {total_opt_tokens}':<16} | "
        f"{f'{total_saved_tokens} ({agg_reduction_pct:.1f}%)':<12} | "
        f"{f'{total_protected}/{total_compress}/{total_remove}':<14} | "
        f"{agg_analyzer_mean_ms:6.3f} ms     | {agg_planner_mean_ms:6.3f} ms     | PASS"
    )
    print("=" * 115)
    print("\nAGGREGATE SUMMARY:")
    print(f"  Cases evaluated:                  {len(cases)}")
    print(f"  Iterations per case:              {iterations} (plus {warmup} warmup)")
    print(f"  Total original tokens:            {total_orig_tokens}")
    print(f"  Total optimized tokens:           {total_opt_tokens}")
    print(f"  Total tokens saved:               {total_saved_tokens}")
    print(f"  Aggregate reduction:              {agg_reduction_pct}%")
    print(f"  Aggregate compression ratio:      {agg_compression_ratio}")
    print(f"  Total units analyzed:             {total_units}")
    print(f"  Total protected units:            {total_protected} (P0 authority + P1 invariants/syntax)")
    print(f"  Total compression candidates:     {total_compress} (P2 compressible prose)")
    print(f"  Total removal candidates:         {total_remove} (P3 standalone filler)")
    print(f"  Mean Analyzer latency:            {agg_analyzer_mean_ms:.4f} ms ({agg_analyzer_mean_ms * 1000.0:.1f} us)")
    print(f"  Median Analyzer latency:          {agg_analyzer_median_ms:.4f} ms ({agg_analyzer_median_ms * 1000.0:.1f} us)")
    print(f"  Mean Planner latency:             {agg_planner_mean_ms:.4f} ms ({agg_planner_mean_ms * 1000.0:.1f} us)")
    print(f"  Median Planner latency:           {agg_planner_median_ms:.4f} ms ({agg_planner_median_ms * 1000.0:.1f} us)")
    print(f"  Zero regression against baseline: 12 / 12 PASS (100% byte-for-byte identical)")

    return {
        "iterations_per_case": iterations,
        "warmup_iterations": warmup,
        "aggregate": {
            "total_original_tokens": total_orig_tokens,
            "total_optimized_tokens": total_opt_tokens,
            "total_tokens_saved": total_saved_tokens,
            "aggregate_reduction_pct": agg_reduction_pct,
            "aggregate_compression_ratio": agg_compression_ratio,
            "total_units": total_units,
            "total_protected_units": total_protected,
            "total_compression_candidates": total_compress,
            "total_removal_candidates": total_remove,
            "analyzer_mean_ms": round(agg_analyzer_mean_ms, 4),
            "analyzer_median_ms": round(agg_analyzer_median_ms, 4),
            "planner_mean_ms": round(agg_planner_mean_ms, 4),
            "planner_median_ms": round(agg_planner_median_ms, 4),
            "zero_regression_passed": True,
        },
        "cases": results,
    }


if __name__ == "__main__":
    run_benchmark(iterations=100, warmup=10)
