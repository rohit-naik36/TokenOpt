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


def explain(metrics: RequestMetrics) -> None:
    """Explain what happened, derived only from the recorded metrics.

    Every line follows from a real metric value, so the explanation can
    never drift from what the pipeline actually did.
    """
    lines: list[str] = []
    if metrics.cache_hit:
        lines.append("Cache hit: the same prompt was seen before, so the model "
                     "call was skipped entirely (near-zero latency).")
    if metrics.compression_effective:
        lines.append(
            f"Compression removed {metrics.tokens_saved} tokens "
            f"({metrics.reduction_percentage:.1f}%): "
            f"{metrics.original_tokens} -> {metrics.optimized_tokens}."
        )
    elif metrics.compression_attempted:
        lines.append("Compression ran but found nothing to remove - the prompt "
                     "was already concise.")
    if metrics.summarization_applied:
        lines.append("Summarization condensed the conversation history because "
                     "it exceeded the configured token threshold.")
    if metrics.routing_reason:
        verb = "Routing picked" if metrics.routing_applied else "Routing kept"
        lines.append(f"{verb} {metrics.model} ({metrics.routing_reason}).")
    if not metrics.cache_hit and metrics.model_latency_ms > 0:
        share = metrics.pipeline_latency_ms / metrics.latency_ms * 100
        lines.append(
            f"TokenOpt overhead was {_fmt_ms(metrics.pipeline_latency_ms)} "
            f"({share:.1f}% of total) vs {_fmt_ms(metrics.model_latency_ms)} "
            f"of model inference."
        )
    if not lines:
        lines.append("Passthrough: no optimization was triggered for this request.")
    print("Why:")
    for line in lines:
        print(f"  - {line}")


def print_comparison(title: str, before: RequestMetrics, after: RequestMetrics) -> None:
    """Print a before/after comparison of two requests' metrics."""
    def row(label: str, m: RequestMetrics) -> str:
        return (
            f"{label}: model={m.model}, {m.original_tokens} -> "
            f"{m.optimized_tokens} tokens ({m.reduction_percentage:.1f}% saved), "
            f"cache={m.cache_hit}"
        )
    print(f"{title}")
    print(f"  {row('Off ', before)}")
    print(f"  {row('On  ', after)}")
