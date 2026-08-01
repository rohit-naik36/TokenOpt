"""Shared helpers for example scripts: clean console output.

TokenOpt logs structured JSON events at INFO level (great for production
monitoring). Examples prefer concise, human-readable output instead, so they
call :func:`quiet` to suppress INFO logging and :func:`print_request` /
:func:`print_summary` to render per-request and aggregated metrics.
"""

from __future__ import annotations

import logging
from typing import Any

from tokenopt import RequestMetrics


def quiet() -> None:
    """Silence TokenOpt's structured INFO logging for clean example output.

    WARNING+ messages (e.g. real errors) still surface. Structured JSON
    logging is unchanged for production use; only this process is quieted.
    """
    logging.getLogger("tokenopt").setLevel(logging.WARNING)
    logging.disable(logging.INFO)


def _fmt_ms(value: float) -> str:
    """Format a millisecond value as ms or s, whichever reads better."""
    if value >= 1000:
        return f"{value / 1000:.2f} s"
    return f"{value:.1f} ms"


def print_request(metrics: RequestMetrics, response: str | None = None) -> None:
    """Print one request's metrics as a readable block."""
    print("Request metrics:")
    print(f"  Model:           {metrics.model}")
    print(f"  Cache hit:       {'Yes' if metrics.cache_hit else 'No'}")
    saved_str = f"{metrics.tokens_saved:+d}" if metrics.tokens_saved else "0"
    print(
        "  Compression:     "
        f"{'attempted' if metrics.compression_attempted else 'not attempted'} / "
        f"{'effective' if metrics.compression_effective else 'no reduction'} "
        f"({saved_str} tokens, {metrics.reduction_percentage:.1f}%)"
    )
    print(
        "  Tokens:          "
        f"{metrics.original_tokens} -> {metrics.optimized_tokens} "
        f"(+{metrics.output_tokens} output)"
    )
    print(
        "  Latency:         "
        f"total {_fmt_ms(metrics.latency_ms)} | "
        f"model {_fmt_ms(metrics.model_latency_ms)} | "
        f"TokenOpt overhead {_fmt_ms(metrics.pipeline_latency_ms)}"
    )
    print(f"  Estimated cost:  ${metrics.estimated_cost:.6f}")
    if response is not None:
        short = response if len(response) <= 120 else response[:117] + "..."
        print(f"  Response:        {short}")


def print_summary(summary: dict[str, Any]) -> None:
    """Print the aggregated metrics summary as readable lines."""
    print("Aggregated metrics:")
    print(f"  Requests:            {summary['total_requests']}")
    print(f"  Cache hit rate:      {summary['cache_hit_rate']:.1%}")
    print(f"  Avg tokens reduced:  {summary['avg_token_reduction']:.1f} "
          f"({summary['avg_token_reduction_pct']:.1f}%)")
    print(f"  Total estimated cost: ${summary['total_estimated_cost']:.6f}")
    print(f"  Error rate:          {summary['error_rate']:.1%}")
    print(
        "  Optimization usage: "
        f"compression {summary['optimization_usage']['compression']} | "
        f"summarization {summary['optimization_usage']['summarization']} | "
        f"routing {summary['optimization_usage']['routing']}"
    )
