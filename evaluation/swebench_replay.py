"""Replay real SWE-bench prompts through the TokenOpt optimizer (offline).

Purpose
-------
Measure the deterministic optimizer's input-token reduction and preservation
decision on a **public, non-synthetic** corpus of developer prose — the
SWE-bench issue/problem statements. This complements the AAVA static-agent
benchmark with prompts nobody on this project authored, removing the
overfitting risk of hand-written cases.

What this measures
------------------
- Input-token reduction of the prompt text, counted with the o200k tokenizer.
- The Validator's ACCEPT/REJECT decision and whether a rollback was applied.

What this does NOT measure (out of scope, and infeasible here)
--------------------------------------------------------------
- SWE-bench's real metric (does an agent's patch resolve the issue and pass
  tests). No model inference, no repository checkout, no patch application.
- Answer quality or downstream reasoning. Token counts are **diagnostic
  estimates** (tokenizer-based), never provider-reported billing.

Data
----
Two ways to supply instances (each row needs an ``instance_id`` and a
``problem_statement``; ``hints_text`` is optional):

1. ``--data path.jsonl`` — a local JSON Lines file (one object per line).
2. ``--dataset princeton-nlp/SWE-bench_Lite`` — loaded via the optional
   ``datasets`` package (``pip install datasets``); requires network on first
   use. Used only when ``--data`` is not given.

Usage
-----
    python evaluation/swebench_replay.py --data swebench_lite.jsonl --limit 100
    python evaluation/swebench_replay.py --dataset princeton-nlp/SWE-bench_Lite --split test
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ruff: noqa: E402
import tiktoken

from tokenopt.config import get_prototype_config
from tokenopt.optimizer import CanonicalOptimizer

_ENC = tiktoken.get_encoding("o200k_base")


def count_tokens(text: str) -> int:
    """Diagnostic token count (o200k). Not provider-reported usage."""
    return len(_ENC.encode(text))


def build_prompt(instance: dict[str, Any], include_hints: bool) -> str:
    """Assemble the natural-language prompt for one SWE-bench instance."""
    parts = [str(instance.get("problem_statement") or "").strip()]
    if include_hints:
        hints = str(instance.get("hints_text") or "").strip()
        if hints:
            parts.append(hints)
    return "\n\n".join(p for p in parts if p)


def load_instances(
    data: Path | None, dataset: str, split: str, limit: int | None
) -> Iterator[dict[str, Any]]:
    """Yield instance dicts from a local JSONL file or the ``datasets`` hub."""
    if data is not None:
        with data.open(encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if limit is not None and i >= limit:
                    return
                line = line.strip()
                if line:
                    yield json.loads(line)
        return

    try:
        from datasets import load_dataset  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise SystemExit(
            "No --data file given and the optional 'datasets' package is not "
            "installed. Either pass --data <jsonl> or run "
            "`pip install datasets` (network required on first load)."
        ) from exc

    ds = load_dataset(dataset, split=split)
    for i, row in enumerate(ds):
        if limit is not None and i >= limit:
            return
        yield dict(row)


def replay(prompt: str, optimizer: CanonicalOptimizer) -> dict[str, Any]:
    """Run one prompt through the optimizer; return token + decision metrics."""
    orig = count_tokens(prompt)
    result = optimizer.optimize([{"role": "user", "content": prompt}], model="gpt-4o")
    opt_text = str(result.optimized_messages[0]["content"]) if result.optimized_messages else prompt
    opt = count_tokens(opt_text)
    saved_pct = (orig - opt) / orig * 100 if orig else 0.0
    tm = result.transformer_metrics
    return {
        "orig_tokens": orig,
        "optimized_tokens": opt,
        "saved_tokens": orig - opt,
        "saved_pct": round(saved_pct, 3),
        "validation_decision": result.validation_decision,
        "rollback_applied": result.rollback_applied,
        "sentences_pruned": tm.get("sentences_pruned", 0),
        "p2_prose_transformed": tm.get("p2_prose_transformed", 0),
    }


def bucket(saved_pct: float) -> str:
    """Assign a saving percentage to a reporting bucket."""
    if saved_pct <= 0.0001:
        return "0%"
    if saved_pct <= 0.5:
        return ">0-0.5%"
    if saved_pct <= 1:
        return ">0.5-1%"
    if saved_pct <= 5:
        return ">1-5%"
    return ">5%"


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-instance rows into corpus-level metrics."""
    total_orig = sum(r["orig_tokens"] for r in rows)
    total_opt = sum(r["optimized_tokens"] for r in rows)
    pcts = [r["saved_pct"] for r in rows]
    buckets: dict[str, int] = {"0%": 0, ">0-0.5%": 0, ">0.5-1%": 0, ">1-5%": 0, ">5%": 0}
    for r in rows:
        buckets[bucket(r["saved_pct"])] += 1
    return {
        "instances": len(rows),
        "tokenizer": "o200k_base",
        "measurement_basis": "diagnostic_estimate_not_provider_reported",
        "total_orig_tokens": total_orig,
        "total_optimized_tokens": total_opt,
        "aggregate_saved_pct": round((total_orig - total_opt) / total_orig * 100, 3)
        if total_orig
        else 0.0,
        "median_saved_pct": round(statistics.median(pcts), 3) if pcts else 0.0,
        "mean_saved_pct": round(statistics.mean(pcts), 3) if pcts else 0.0,
        "non_accept": sum(1 for r in rows if r["validation_decision"] != "accept"),
        "rollbacks": sum(1 for r in rows if r["rollback_applied"]),
        "distribution": buckets,
    }


def print_summary(summary: dict[str, Any]) -> None:
    """Print a human-readable summary to stdout."""
    print(f"\nSWE-bench replay — {summary['instances']} instances (o200k, diagnostic estimate)")
    print(
        f"  input {summary['total_orig_tokens']:,} -> {summary['total_optimized_tokens']:,} "
        f"tokens  ({summary['aggregate_saved_pct']}% saved)"
    )
    print(
        f"  per-instance saving: median {summary['median_saved_pct']}%  "
        f"mean {summary['mean_saved_pct']}%"
    )
    print(f"  non-accept={summary['non_accept']}  rollbacks={summary['rollbacks']}")
    print("  distribution:")
    for label, count in summary["distribution"].items():
        share = count / summary["instances"] * 100 if summary["instances"] else 0.0
        print(f"    {label:<9} {count:>6}  ({share:.0f}%)")


# ---------------------------------------------------------------------------
# Trajectory mode: replay recorded SWE-agent runs turn by turn
# ---------------------------------------------------------------------------
# The optimizer is run at every assistant turn on the cumulative message list
# (system + demonstration + issue + all prior action/observation pairs), which
# is what a gateway would see per LLM call. NOTE: SWE-agent windows/elides old
# observations at runtime, so this cumulative reconstruction is an UPPER BOUND
# on tokens actually sent; treat per-run totals as an estimate, not billing.
# `enable_compression` (the real flag; there is no `content_compression_enabled`)
# is on via get_prototype_config().


def iter_traj_turns(path: Path) -> Iterator[tuple[int, list[dict[str, Any]]]]:
    """Yield (turn_number, cumulative message list) for each assistant turn."""
    traj = json.loads(path.read_text(encoding="utf-8"))
    history = traj.get("history") or []
    turn = 0
    for j, msg in enumerate(history):
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            turn += 1
            messages = [
                {"role": str(m.get("role")), "content": str(m.get("content", ""))}
                for m in history[:j]
                if isinstance(m, dict)
            ]
            if messages:
                yield turn, messages


def replay_trajectory(path: Path, optimizer: CanonicalOptimizer) -> dict[str, Any]:
    """Replay one trajectory; return per-turn and per-run token metrics."""
    turns: list[dict[str, Any]] = []
    for turn, messages in iter_traj_turns(path):
        orig = sum(count_tokens(m["content"]) for m in messages)
        result = optimizer.optimize([dict(m) for m in messages], model="gpt-4o")
        opt = sum(count_tokens(str(m.get("content", ""))) for m in result.optimized_messages)
        tm = result.transformer_metrics
        turns.append(
            {
                "turn": turn,
                "messages": len(messages),
                "orig_tokens": orig,
                "optimized_tokens": opt,
                "saved_tokens": orig - opt,
                "saved_pct": round((orig - opt) / orig * 100, 3) if orig else 0.0,
                "validation_decision": result.validation_decision,
                "rollback_applied": result.rollback_applied,
                "rollback_reason": result.rollback_reason,
                "sentences_pruned": tm.get("sentences_pruned", 0),
                "p2_prose_transformed": tm.get("p2_prose_transformed", 0),
            }
        )
    run_orig = sum(t["orig_tokens"] for t in turns)
    run_opt = sum(t["optimized_tokens"] for t in turns)
    return {
        "instance_id": path.stem,
        "turns": len(turns),
        "run_orig_tokens": run_orig,
        "run_optimized_tokens": run_opt,
        "run_saved_pct": round((run_orig - run_opt) / run_orig * 100, 3) if run_orig else 0.0,
        "rollbacks": sum(1 for t in turns if t["rollback_applied"]),
        "turn_detail": turns,
    }


def summarize_trajectories(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate trajectory runs: totals, per-turn-number curve, rollback reasons."""
    all_turns = [t for r in runs for t in r["turn_detail"]]
    total_orig = sum(t["orig_tokens"] for t in all_turns)
    total_opt = sum(t["optimized_tokens"] for t in all_turns)
    by_turn: dict[int, list[float]] = {}
    for t in all_turns:
        by_turn.setdefault(t["turn"], []).append(t["saved_pct"])
    turn_curve = {
        str(k): round(statistics.mean(v), 3) for k, v in sorted(by_turn.items()) if k <= 15
    }
    reasons: dict[str, int] = {}
    for t in all_turns:
        if t["rollback_applied"]:
            reasons[str(t["rollback_reason"])] = reasons.get(str(t["rollback_reason"]), 0) + 1
    run_pcts = [r["run_saved_pct"] for r in runs]
    return {
        "trajectories": len(runs),
        "llm_calls_total": len(all_turns),
        "tokenizer": "o200k_base",
        "measurement_basis": "diagnostic_estimate_cumulative_history_upper_bound",
        "total_orig_tokens": total_orig,
        "total_optimized_tokens": total_opt,
        "aggregate_saved_pct": round((total_orig - total_opt) / total_orig * 100, 3)
        if total_orig
        else 0.0,
        "median_run_saved_pct": round(statistics.median(run_pcts), 3) if run_pcts else 0.0,
        "total_rollbacks": sum(r["rollbacks"] for r in runs),
        "saved_pct_by_turn_number": turn_curve,
        "rollback_reasons": reasons,
    }


def print_traj_summary(summary: dict[str, Any]) -> None:
    """Print a human-readable trajectory summary."""
    print(
        f"\nSWE-agent trajectory replay — {summary['trajectories']} runs, "
        f"{summary['llm_calls_total']} LLM calls (o200k, cumulative upper bound)"
    )
    print(
        f"  input {summary['total_orig_tokens']:,} -> {summary['total_optimized_tokens']:,} "
        f"tokens  ({summary['aggregate_saved_pct']}% saved)"
    )
    print(f"  median per-run saving: {summary['median_run_saved_pct']}%")
    print(f"  total rollbacks: {summary['total_rollbacks']} of {summary['llm_calls_total']} calls")
    print("  saved% by turn number (mean):")
    for turn, pct in summary["saved_pct_by_turn_number"].items():
        print(f"    turn {turn:<3} {pct}%")
    if summary["rollback_reasons"]:
        print("  rollback reasons:")
        for reason, count in sorted(summary["rollback_reasons"].items(), key=lambda x: -x[1]):
            print(f"    {count:>5}  {reason[:70]}")


def run_trajectory_mode(trajs_dir: Path, limit: int | None, out: Path) -> None:
    """Replay every .traj under a directory and report."""
    files = sorted(trajs_dir.glob("*.traj"))
    if limit is not None:
        files = files[:limit]
    if not files:
        raise SystemExit(f"No .traj files found under {trajs_dir}")
    optimizer = CanonicalOptimizer(get_prototype_config())
    runs = [replay_trajectory(f, optimizer) for f in files]
    summary = summarize_trajectories(runs)
    print_traj_summary(summary)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "runs": runs}, indent=1), encoding="utf-8")
    print(f"\nwrote {out}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Replay SWE-bench prompts through the TokenOpt optimizer."
    )
    src = ap.add_argument_group("data source")
    src.add_argument("--data", type=Path, help="Local JSONL file of SWE-bench instances.")
    src.add_argument(
        "--dataset", default="princeton-nlp/SWE-bench_Lite", help="HuggingFace dataset id."
    )
    src.add_argument("--split", default="test", help="Dataset split (when using --dataset).")
    src.add_argument(
        "--trajs",
        type=Path,
        help="Directory of SWE-agent .traj files; enables turn-by-turn trajectory replay.",
    )
    ap.add_argument(
        "--limit", type=int, default=None, help="Cap instances or trajectories."
    )
    ap.add_argument("--include-hints", action="store_true", help="Append hints_text to the prompt.")
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Where to write the machine-readable report.",
    )
    args = ap.parse_args()

    if args.trajs is not None:
        out = args.out or REPO_ROOT / "evaluation" / "results" / "swebench_trajs_replay.json"
        run_trajectory_mode(args.trajs, args.limit, out)
        return

    out = args.out or REPO_ROOT / "evaluation" / "results" / "swebench_replay.json"
    optimizer = CanonicalOptimizer(get_prototype_config())
    rows: list[dict[str, Any]] = []
    for instance in load_instances(args.data, args.dataset, args.split, args.limit):
        prompt = build_prompt(instance, args.include_hints)
        if not prompt:
            continue
        row = {"instance_id": instance.get("instance_id"), **replay(prompt, optimizer)}
        rows.append(row)

    if not rows:
        raise SystemExit("No instances with a usable problem_statement were found.")

    summary = summarize(rows)
    print_summary(summary)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "instances": rows}, indent=1), encoding="utf-8")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
