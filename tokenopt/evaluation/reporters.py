"""Reporters for TokenOpt Evidence Harness (JSONL, CSV, Markdown)."""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from pathlib import Path

from tokenopt.evaluation.schema import EvidenceRecord, TaskFidelityStatus


class EvidenceReporter:
    """Exports paired evidence records to JSONL, CSV, and Markdown formats."""

    def __init__(self, records: Sequence[EvidenceRecord]):
        self.records = list(records)

    def write_jsonl(self, file_path: str | Path) -> None:
        """Write raw evidence records as JSON Lines."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for rec in self.records:
                f.write(json.dumps(rec.to_dict()) + "\n")

    def write_json(self, file_path: str | Path) -> None:
        """Write raw evidence records as formatted JSON array."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump([rec.to_dict() for rec in self.records], f, indent=2)

    def write_csv(self, file_path: str | Path) -> None:
        """Write tabular summary to CSV."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [
            "run_id",
            "case_id",
            "category",
            "provider",
            "model",
            "environment",
            "execution_status",
            "base_in_tokens",
            "opt_in_tokens",
            "tokens_saved",
            "reduction_pct",
            "val_decision",
            "rollback_applied",
            "invariants_passed",
            "invariants_checked",
            "task_fidelity_status",
            "base_task_passed",
            "opt_task_passed",
            "pipe_lat_ms",
            "base_lat_ms",
            "opt_lat_ms",
            "cost_saved_proj",
            "requested_params",
            "effective_params",
        ]

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for rec in self.records:
                b_in = rec.baseline.provider_input_tokens
                t_in = rec.tokenopt.provider_input_tokens
                saved = rec.comparison.provider_tokens_saved
                red_pct = rec.comparison.provider_reduction_pct

                writer.writerow({
                    "run_id": rec.run_id,
                    "case_id": rec.case_id,
                    "category": rec.category,
                    "provider": rec.provider,
                    "model": rec.model,
                    "environment": rec.execution_environment,
                    "execution_status": rec.execution_status.value,
                    "base_in_tokens": b_in if b_in is not None else "N/A",
                    "opt_in_tokens": t_in if t_in is not None else "N/A",
                    "tokens_saved": saved if saved is not None else "N/A",
                    "reduction_pct": f"{red_pct:.2f}%" if red_pct is not None else "N/A",
                    "val_decision": rec.preservation.validation_decision,
                    "rollback_applied": rec.preservation.rollback_applied,
                    "invariants_passed": rec.preservation.invariants_passed,
                    "invariants_checked": rec.preservation.invariants_checked,
                    "task_fidelity_status": rec.task_fidelity.status.value,
                    "base_task_passed": rec.task_fidelity.baseline_passed,
                    "opt_task_passed": rec.task_fidelity.tokenopt_passed,
                    "pipe_lat_ms": (
                        f"{rec.tokenopt.pipeline_latency_ms:.2f}"
                        if rec.tokenopt.pipeline_latency_ms is not None
                        else "N/A"
                    ),
                    "base_lat_ms": (
                        f"{rec.baseline.total_latency_ms:.2f}"
                        if rec.baseline.total_latency_ms is not None
                        else "N/A"
                    ),
                    "opt_lat_ms": (
                        f"{rec.tokenopt.total_latency_ms:.2f}"
                        if rec.tokenopt.total_latency_ms is not None
                        else "N/A"
                    ),
                    "cost_saved_proj": (
                        f"${rec.comparison.projected_cost_saved:.6f}"
                        if rec.comparison.projected_cost_saved is not None
                        else "N/A"
                    ),
                    "requested_params": json.dumps(
                        getattr(rec, "requested_generation_parameters", rec.generation_parameters)
                    ),
                    "effective_params": (
                        json.dumps(rec.effective_generation_parameters)
                        if getattr(rec, "effective_generation_parameters", None) is not None
                        else "N/A"
                    ),
                })

    def generate_markdown(self) -> str:
        """Generate human-readable Markdown report distinguishing metric classes."""
        if not self.records:
            return "# TokenOpt Evidence Report\n\nNo records to report."

        first = self.records[0]
        run_id = first.run_id
        model = first.model
        provider = first.provider
        exec_env = first.execution_environment
        timestamp = first.timestamp

        total_cases = len(self.records)
        successful_runs = sum(
            1 for r in self.records if r.execution_status.value == "success"
        )
        rollbacks = sum(1 for r in self.records if r.preservation.rollback_applied)
        val_accepted = sum(
            1 for r in self.records if r.preservation.validation_decision == "accept"
        )

        # Aggregations for tokens where valid
        base_tok_sum = sum(
            r.baseline.provider_input_tokens
            for r in self.records
            if r.baseline.provider_input_tokens is not None
        )
        opt_tok_sum = sum(
            r.tokenopt.provider_input_tokens
            for r in self.records
            if r.tokenopt.provider_input_tokens is not None
        )
        has_provider_tokens = all(
            r.baseline.provider_input_tokens is not None
            and r.tokenopt.provider_input_tokens is not None
            for r in self.records
        )
        total_tokens_saved = base_tok_sum - opt_tok_sum if has_provider_tokens else None
        agg_reduction_pct = (
            round((total_tokens_saved / base_tok_sum) * 100.0, 2)
            if has_provider_tokens and base_tok_sum > 0 and total_tokens_saved is not None
            else None
        )

        total_cost_saved = sum(
            r.comparison.projected_cost_saved
            for r in self.records
            if r.comparison.projected_cost_saved is not None
        )

        # Task fidelity stats
        evaluated_tasks = [
            r for r in self.records
            if r.task_fidelity.status != TaskFidelityStatus.NOT_EVALUATED
        ]
        task_passed = sum(
            1 for r in evaluated_tasks
            if r.task_fidelity.status == TaskFidelityStatus.PASSED
        )
        n_eval = len(evaluated_tasks)
        n_na = total_cases - n_eval

        cost_line = (
            f"| Projected Cost Saved | **Projected** | ${total_cost_saved:.6f} | "
            f"Based on published table rates ($/1M tokens) |"
            if exec_env != "local_compute"
            else "| Provider Billing Cost | **Observed (Local)** | $0.00 | "
                 "Local compute (no provider billing) |"
        )

        tok_line = (
            f"| Provider Input Tokens | **Observed** | {base_tok_sum} -> {opt_tok_sum} "
            f"({total_tokens_saved} saved, {agg_reduction_pct}%) | Provider-reported usage |"
            if has_provider_tokens
            else "| Provider Input Tokens | **Unavailable** | N/A | "
                 "Provider did not return usage metrics |"
        )

        req_params = (
            first.requested_generation_parameters
            if hasattr(first, "requested_generation_parameters")
            and first.requested_generation_parameters
            else first.generation_parameters
        )
        eff_params = getattr(first, "effective_generation_parameters", None)

        req_str = json.dumps(req_params, indent=2) if req_params else "{}"
        eff_str = (
            json.dumps(eff_params, indent=2)
            if eff_params is not None
            else "null (not reliably exposed by provider)"
        )

        lines: list[str] = [
            "# TokenOpt Prototype v0.2: Empirical Evidence Report",
            "",
            f"**Run ID:** `{run_id}`  ",
            f"**Timestamp:** `{timestamp}`  ",
            f"**Provider:** `{provider}` | **Model:** `{model}`  ",
            f"**Execution Environment:** `{exec_env}`  ",
            "",
            "### Generation Parameters Configuration",
            "",
            "**Requested Parameters:**",
            f"```json\n{req_str}\n```",
            "",
            "**Effective Parameters (Provider/Model Defaults):**",
            f"```json\n{eff_str}\n```",
            "",
            "---",
            "",
            "## Executive Summary",
            "",
            "| Metric Dimension | Classification | Value | Notes |",
            "|---|---|---|---|",
            f"| Evaluated Cases | **Observed** | "
            f"{total_cases} total / {successful_runs} successful | "
            "All cases paired Baseline vs TokenOpt |",
            f"| Preservation Decision | **Observed** | {val_accepted}/{total_cases} ACCEPT "
            f"({rollbacks} rollbacks) | Emitted directly by ValidatorStage |",
            tok_line,
            cost_line,
            f"| Task Fidelity Pass Rate | **Observed** | {task_passed}/{n_eval} "
            f"({n_eval} evaluated, {n_na} N/A) | Deterministic task assertions |",
            "",
            "---",
            "",
            "## Case-by-Case Comparison Table",
            "",
            "| Case ID | Status | Base In | Opt In | Saved (%) | Val Decision | Rollback | "
            "Task Fidelity | Pipe Latency |",
            "|---|---|---|---|---|---|---|---|---|",
        ]

        for r in self.records:
            b_in = r.baseline.provider_input_tokens
            t_in = r.tokenopt.provider_input_tokens
            saved = r.comparison.provider_tokens_saved
            red_pct = r.comparison.provider_reduction_pct

            in_str = (
                f"{b_in} -> {t_in}"
                if b_in is not None and t_in is not None
                else "N/A"
            )
            saved_str = (
                f"{saved} ({red_pct:.1f}%)"
                if saved is not None and red_pct is not None
                else "N/A"
            )
            task_str = (
                f"{r.task_fidelity.status.value.upper()}"
                if r.task_fidelity.status != TaskFidelityStatus.NOT_EVALUATED
                else "NOT_EVALUATED"
            )
            pipe_lat_str = (
                f"{r.tokenopt.pipeline_latency_ms:.2f} ms"
                if r.tokenopt.pipeline_latency_ms is not None
                else "N/A"
            )

            lines.append(
                f"| `{r.case_id}` | `{r.execution_status.value}` | {in_str} | "
                f"{t_in if t_in is not None else 'N/A'} | {saved_str} | "
                f"`{r.preservation.validation_decision}` | `{r.preservation.rollback_applied}` | "
                f"`{task_str}` | {pipe_lat_str} |"
            )

        lines.extend([
            "",
            "---",
            "",
            "## Methodological Notes",
            "",
            "1. **Baseline Isolation:** Baseline genuinely bypasses `pipeline.run()`, "
            "invoking provider API directly.",
            "2. **Token Accounting Separation:** Local tiktoken estimates are tracked "
            "independently and never substituted for provider usage.",
            "3. **Cost Classification:** Cloud costs are reported strictly as *Projected Costs* "
            "based on published token prices. Local compute environments incur zero "
            "provider billing.",
            "4. **Preservation Fidelity:** Direct pass-through from "
            "`tokenopt/pipeline/validator.py`. No secondary evaluator introduced.",
            "5. **Task Fidelity Boundary:** Strictly evaluates deterministic constraints on "
            "the 6 qualified cases. Open-ended conversational cases are explicitly designated "
            "`NOT_EVALUATED`.",
        ])

        return "\n".join(lines) + "\n"

    def write_markdown(self, file_path: str | Path) -> None:
        """Write human-readable report to Markdown file."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = self.generate_markdown()
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
