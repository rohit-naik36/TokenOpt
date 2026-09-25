"""CLI runner for TokenOpt Prototype v0.2 Evidence Harness."""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ruff: noqa: E402
from evaluation.cases import get_cases
from tokenopt.clients.base import BaseOptimizedClient
from tokenopt.config import get_prototype_config
from tokenopt.evaluation.harness import EvidenceHarness
from tokenopt.evaluation.reporters import EvidenceReporter
from tokenopt.factory import create_client


class MockEvidenceClient(BaseOptimizedClient):
    """Deterministic in-memory mock client for CI verification without network calls."""

    def __init__(self, model: str = "llama3.1"):
        super().__init__(config=get_prototype_config())
        self.default_local_model = model

    def _create_client(self) -> Any:
        return None

    def _call_api(self, messages: list[dict[str, Any]], model: str, **kwargs: Any) -> Any:
        # Determine deterministic answer based on prompt content
        full_text = " ".join(
            str(m.get("content", "")) for m in messages if isinstance(m.get("content"), str)
        )

        content = "Understood. Executing request."
        if "[EXEC-SUMMARY]" in full_text or "Level-4" in full_text:
            content = (
                "[EXEC-SUMMARY]\n"
                "- Enforced strict Level-4 security compliance across all clusters.\n"
                "- Migrated database tier to isolated network segment.\n"
                "- Verified audit logging and telemetry pipelines are active."
            )
        elif "2026-01-15" in full_text or "Phase-2" in full_text:
            content = "The delivery for Phase-2 is confirmed for 2026-01-15."
        elif "node_count" in full_text:
            content = "The cluster node_count is 12."
        elif "SLA Breach" in full_text or "EU-Central" in full_text:
            content = (
                "Based on the table, EU-Central experienced an SLA Breach "
                "with 99.850% availability."
            )
        elif "DOC-403" in full_text:
            content = (
                "Per DOC-403, a Sev-1 incident notification must be sent to "
                "security-ops@acme.corp within 15 minutes."
            )
        elif "CRITICAL_ALERT_ASSERTION" in full_text:
            content = (
                "Alert acknowledged: Node-99 encountered fatal panic with error KERN-ERR-0x89AB."
            )

        # Mock token accounting
        prompt_tokens = sum(len(str(m.get("content", "")).split()) for m in messages)
        completion_tokens = len(content.split())

        return SimpleNamespace(
            id=f"mock-cmpl-{uuid.uuid4().hex[:8]}",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content, role="assistant"),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )

    def _extract_response_content(self, response: Any) -> str:
        return str(response.choices[0].message.content)

    def _extract_usage(self, response: Any) -> dict[str, int]:
        return {
            "prompt_tokens": int(response.usage.prompt_tokens),
            "completion_tokens": int(response.usage.completion_tokens),
            "total_tokens": int(response.usage.total_tokens),
        }


def run_evidence_cli(args: list[str] | None = None) -> int:
    """CLI execution entrypoint."""
    parser = argparse.ArgumentParser(description="TokenOpt Prototype v0.2 Evidence Harness")
    parser.add_argument("--model", type=str, default="llama3.1", help="Target model name")
    parser.add_argument("--provider", type=str, default="ollama", help="Provider name")
    parser.add_argument(
        "--output-dir", type=str, default="evaluation/results", help="Directory for artifacts"
    )
    parser.add_argument("--run-id", type=str, default=None, help="Optional run identifier")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run with mock provider (no LLM required)",
    )
    parser.add_argument(
        "--semantic", action="store_true", help="Enable diagnostic semantic similarity"
    )

    parsed = parser.parse_args(args)

    run_id = parsed.run_id or f"run-{uuid.uuid4().hex[:12]}"
    print(f"Starting Evidence Harness run: {run_id}")
    print(f"Model: {parsed.model} | Provider: {parsed.provider} | Mock: {parsed.mock}")

    client: BaseOptimizedClient
    if parsed.mock:
        client = MockEvidenceClient(model=parsed.model)
    else:
        client = create_client(model=parsed.model, config=get_prototype_config())

    harness = EvidenceHarness(
        client=client,
        model=parsed.model,
        provider_name="mock" if parsed.mock else parsed.provider,
        enable_semantic_diagnostics=parsed.semantic,
    )

    print(f"Requested Parameters: {harness.generation_parameters}")
    print(f"Effective Parameters: {harness.effective_generation_parameters}")

    cases = get_cases()
    print(f"Executing {len(cases)} paired cases (Baseline vs TokenOpt)...")

    records = harness.run_all(cases, run_id=run_id)

    # Export artifacts
    out_dir = Path(parsed.output_dir)
    reporter = EvidenceReporter(records)

    jsonl_path = out_dir / f"evidence_{run_id}.jsonl"
    csv_path = out_dir / f"evidence_{run_id}.csv"
    md_path = out_dir / f"evidence_{run_id}.md"

    reporter.write_jsonl(jsonl_path)
    reporter.write_csv(csv_path)
    reporter.write_markdown(md_path)

    print("\nEvidence Artifacts Generated:")
    print(f"  JSONL: {jsonl_path}")
    print(f"  CSV:   {csv_path}")
    print(f"  MD:    {md_path}")

    # Terminal summary table
    print("\n" + "=" * 90)
    print(f"TOKENOPT EVIDENCE HARNESS SUMMARY (Run: {run_id})")
    print("=" * 90)
    print(
        f"{'Case ID':<28} | {'Status':<10} | {'Base In':<8} | {'Opt In':<8} | "
        f"{'Saved':<7} | {'Val Dec':<8} | {'Task':<10}"
    )
    print("-" * 90)
    for r in records:
        b_in = r.baseline.provider_input_tokens
        t_in = r.tokenopt.provider_input_tokens
        saved = r.comparison.provider_tokens_saved
        b_str = str(b_in) if b_in is not None else "N/A"
        t_str = str(t_in) if t_in is not None else "N/A"
        s_str = str(saved) if saved is not None else "N/A"
        print(
            f"{r.case_id:<28} | {r.execution_status.value:<10} | {b_str:<8} | "
            f"{t_str:<8} | {s_str:<7} | {r.preservation.validation_decision:<8} | "
            f"{r.task_fidelity.status.value:<10}"
        )
    print("=" * 90)

    return 0


if __name__ == "__main__":
    sys.exit(run_evidence_cli())
