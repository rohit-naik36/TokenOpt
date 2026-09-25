"""Focused tests for CP8 — Evidence Boundary & Claim Integrity.

These tests verify the strict separation between LOCAL_ESTIMATE (diagnostic)
and PROVIDER_OBSERVATION (observed) measurement classes, and that reporters
make the measurement basis explicit.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from tokenopt.clients.base import BaseOptimizedClient
from tokenopt.config import get_prototype_config
from tokenopt.evaluation.adapters import (
    TokenOptAdapter,
    _ContextCaptureStage,
    extract_provider_usage_safe,
)
from tokenopt.evaluation.harness import EvidenceHarness
from tokenopt.evaluation.reporters import EvidenceReporter
from tokenopt.evaluation.schema import (
    ExecutionStatus,
    TaskFidelityStatus,
)
from tokenopt.pipeline.base import OptimizationContext


class DummyClient(BaseOptimizedClient):
    """Stub client for testing without live LLM calls."""

    def __init__(self, usage_available: bool = True, model: str = "gpt-4o-mini"):
        super().__init__(config=get_prototype_config())
        self.usage_available = usage_available
        self.default_model_name = model
        self.api_call_count = 0

    def _create_client(self) -> Any:
        return MagicMock()

    def _call_api(self, messages: list[dict[str, Any]], model: str, **kwargs: Any) -> Any:
        self.api_call_count += 1
        prompt_len = sum(len(str(m.get("content", "")).split()) for m in messages)

        usage = (
            SimpleNamespace(
                prompt_tokens=prompt_len,
                completion_tokens=10,
                total_tokens=prompt_len + 10,
            )
            if self.usage_available
            else None
        )

        return SimpleNamespace(
            id="dummy-cmpl-123",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="[EXEC-SUMMARY]\n- One\n- Two\n- Three\nLevel-4 verified.",
                        role="assistant",
                    ),
                    finish_reason="stop",
                )
            ],
            usage=usage,
        )

    def _extract_response_content(self, response: Any) -> str:
        return str(response.choices[0].message.content)

    def _extract_usage(self, response: Any) -> dict[str, int]:
        if getattr(response, "usage", None):
            return {
                "prompt_tokens": int(response.usage.prompt_tokens),
                "completion_tokens": int(response.usage.completion_tokens),
                "total_tokens": int(response.usage.total_tokens),
            }
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


class TestCP8ProviderTokenReduction:
    """Test that provider token reduction uses ONLY provider-reported input tokens."""

    def test_provider_reduction_uses_only_provider_input_tokens(self) -> None:
        """ComparisonEvidence.provider_tokens_saved must be
        baseline.provider_input - tokenopt.provider_input."""
        client = DummyClient()
        harness = EvidenceHarness(
            client=client,
            model="gpt-4o-mini",
            provider_name="openai",
        )

        cases = harness.run_all(
            [SimpleNamespace(
                id="test_case",
                category="test",
                messages=[{"role": "user", "content": "Hello world"}],
                expected_preserved=[],
            )],
            run_id="test-run"
        )

        rec = cases[0]
        # Provider input tokens saved = baseline.provider_input - tokenopt.provider_input
        b_in = rec.baseline.provider_input_tokens
        t_in = rec.tokenopt.provider_input_tokens
        saved = rec.comparison.provider_tokens_saved

        assert saved is not None
        assert saved == b_in - t_in
        # The formula must use provider tokens, not estimates
        # (They may coincidentally be equal in some cases, but the formula is correct)
        assert rec.comparison.provider_tokens_saved == b_in - t_in

    def test_provider_reduction_pct_uses_provider_baseline(self) -> None:
        """provider_reduction_pct must be (saved / baseline.provider_input) * 100."""
        client = DummyClient()
        harness = EvidenceHarness(
            client=client,
            model="gpt-4o-mini",
            provider_name="openai",
        )

        cases = harness.run_all(
            [SimpleNamespace(
                id="test_case",
                category="test",
                messages=[{"role": "user", "content": "Hello world"}],
                expected_preserved=[],
            )],
            run_id="test-run"
        )

        rec = cases[0]
        b_in = rec.baseline.provider_input_tokens
        saved = rec.comparison.provider_tokens_saved
        red_pct = rec.comparison.provider_reduction_pct

        assert red_pct is not None
        expected = round((saved / b_in) * 100.0, 2)
        assert red_pct == expected


class TestCP8MissingProviderMeasurements:
    """Test that missing provider measurements produce None, not local estimates."""

    def test_baseline_missing_provider_tokens_returns_none(self) -> None:
        """When provider returns no usage, baseline.provider_input_tokens must be None."""
        client = DummyClient(usage_available=False)
        harness = EvidenceHarness(
            client=client,
            model="gpt-4o-mini",
            provider_name="openai",
        )

        cases = harness.run_all(
            [SimpleNamespace(
                id="test_case",
                category="test",
                messages=[{"role": "user", "content": "Hello world"}],
                expected_preserved=[],
            )],
            run_id="test-run"
        )

        rec = cases[0]
        # Provider tokens must be None, NOT zero
        assert rec.baseline.provider_input_tokens is None
        assert rec.baseline.provider_output_tokens is None
        assert rec.baseline.provider_total_tokens is None

    def test_tokenopt_missing_provider_tokens_returns_none(self) -> None:
        """When provider returns no usage, tokenopt.provider_input_tokens must be None."""
        client = DummyClient(usage_available=False)
        harness = EvidenceHarness(
            client=client,
            model="gpt-4o-mini",
            provider_name="openai",
        )

        cases = harness.run_all(
            [SimpleNamespace(
                id="test_case",
                category="test",
                messages=[{"role": "user", "content": "Hello world"}],
                expected_preserved=[],
            )],
            run_id="test-run"
        )

        rec = cases[0]
        assert rec.tokenopt.provider_input_tokens is None
        assert rec.tokenopt.provider_output_tokens is None
        assert rec.tokenopt.provider_total_tokens is None

    def test_provider_tokens_saved_is_none_when_either_side_missing(self) -> None:
        """provider_tokens_saved must be None if either
        baseline or tokenopt lacks provider tokens."""
        client = DummyClient(usage_available=False)
        harness = EvidenceHarness(
            client=client,
            model="gpt-4o-mini",
            provider_name="openai",
        )

        cases = harness.run_all(
            [SimpleNamespace(
                id="test_case",
                category="test",
                messages=[{"role": "user", "content": "Hello world"}],
                expected_preserved=[],
            )],
            run_id="test-run"
        )

        rec = cases[0]
        assert rec.comparison.provider_tokens_saved is None
        assert rec.comparison.provider_reduction_pct is None

    def test_local_estimates_remain_distinct_when_provider_missing(self) -> None:
        """Local estimates must remain available and distinct even when provider tokens missing."""
        client = DummyClient(usage_available=False)
        harness = EvidenceHarness(
            client=client,
            model="gpt-4o-mini",
            provider_name="openai",
        )

        cases = harness.run_all(
            [SimpleNamespace(
                id="test_case",
                category="test",
                messages=[{"role": "user", "content": "Hello world"}],
                expected_preserved=[],
            )],
            run_id="test-run"
        )

        rec = cases[0]
        # Local estimates always present
        assert rec.tokenopt.estimated_original_tokens > 0
        assert rec.tokenopt.estimated_optimized_tokens >= 0
        assert rec.tokenopt.estimated_tokens_saved >= 0
        # But provider comparison is None
        assert rec.comparison.provider_tokens_saved is None


class TestCP8NoSilentSubstitution:
    """Test that local estimates cannot be silently presented as provider-observed savings."""

    def test_reporter_csv_headers_explicitly_distinguish_bases(self, tmp_path: Path) -> None:
        """CSV headers must distinguish provider_* from estimated_*."""
        client = DummyClient()
        harness = EvidenceHarness(
            client=client,
            model="gpt-4o-mini",
            provider_name="openai",
        )

        cases = harness.run_all(
            [SimpleNamespace(
                id="test_case",
                category="test",
                messages=[{"role": "user", "content": "Hello world"}],
                expected_preserved=[],
            )],
            run_id="test-run"
        )

        reporter = EvidenceReporter(cases)
        csv_path = tmp_path / "test.csv"
        reporter.write_csv(csv_path)

        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames

        # Provider-observed columns
        assert "provider_baseline_input_tokens" in fieldnames
        assert "provider_tokenopt_input_tokens" in fieldnames
        assert "provider_input_tokens_saved" in fieldnames
        assert "provider_input_reduction_pct" in fieldnames

        # Local estimate columns (distinct names)
        assert "estimated_original_tokens" in fieldnames
        assert "estimated_optimized_tokens" in fieldnames
        assert "estimated_tokens_saved" in fieldnames

        # No ambiguous "tokens_saved" or "base_in_tokens"
        assert "tokens_saved" not in fieldnames
        assert "base_in_tokens" not in fieldnames
        assert "opt_in_tokens" not in fieldnames

    def test_reporter_markdown_labels_measurement_basis(self, tmp_path: Path) -> None:
        """Markdown must label provider tokens as 'Provider-Reported' and estimates as 'Est.'."""
        client = DummyClient()
        harness = EvidenceHarness(
            client=client,
            model="gpt-4o-mini",
            provider_name="openai",
        )

        cases = harness.run_all(
            [SimpleNamespace(
                id="test_case",
                category="test",
                messages=[{"role": "user", "content": "Hello world"}],
                expected_preserved=[],
            )],
            run_id="test-run"
        )

        reporter = EvidenceReporter(cases)
        md_path = tmp_path / "test.md"
        reporter.write_markdown(md_path)

        md_content = md_path.read_text(encoding="utf-8")

        # Provider tokens explicitly labeled
        assert "Provider-Reported Input Tokens" in md_content
        assert "Provider Baseline In" in md_content
        assert "Provider TokenOpt In" in md_content
        assert "Provider Saved" in md_content

        # Local estimates explicitly labeled
        assert "Est. Original" in md_content
        assert "Est. Optimized" in md_content
        assert "Est. Saved" in md_content

        # Diagnostic section present
        assert "Local Token Estimates (Diagnostic" in md_content
        assert "**Diagnostic**" in md_content

    def test_reporter_never_mixes_bases_in_same_column(self, tmp_path: Path) -> None:
        """A single column must never mix provider and local estimate values."""
        client = DummyClient(usage_available=False)  # Provider tokens unavailable
        harness = EvidenceHarness(
            client=client,
            model="gpt-4o-mini",
            provider_name="openai",
        )

        cases = harness.run_all(
            [SimpleNamespace(
                id="test_case",
                category="test",
                messages=[{"role": "user", "content": "Hello world"}],
                expected_preserved=[],
            )],
            run_id="test-run"
        )

        reporter = EvidenceReporter(cases)
        csv_path = tmp_path / "test.csv"
        reporter.write_csv(csv_path)

        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            row = next(reader)

        # Provider columns should be N/A
        assert row["provider_baseline_input_tokens"] == "N/A"
        assert row["provider_tokenopt_input_tokens"] == "N/A"
        assert row["provider_input_tokens_saved"] == "N/A"

        # Local estimate columns should have actual values
        assert row["estimated_original_tokens"] != "N/A"
        assert int(row["estimated_original_tokens"]) > 0
        assert row["estimated_optimized_tokens"] != "N/A"
        assert row["estimated_tokens_saved"] != "N/A"


class TestCP8ReporterMeasurementBasis:
    """Test that reporter output identifies the measurement basis."""

    def test_csv_fieldnames_use_clear_naming_convention(self) -> None:
        """CSV fieldnames must use clear naming convention for measurement basis."""
        # Fieldnames defined in write_csv; verified by test_reporter_csv_headers_explicit
        pass

    def test_markdown_executive_summary_has_classification_column(self, tmp_path: Path) -> None:
        """Markdown executive summary must have Classification column with OBSERVED/DIAGNOSTIC."""
        client = DummyClient()
        harness = EvidenceHarness(
            client=client,
            model="gpt-4o-mini",
            provider_name="openai",
        )

        cases = harness.run_all(
            [SimpleNamespace(
                id="test_case",
                category="test",
                messages=[{"role": "user", "content": "Hello world"}],
                expected_preserved=[],
            )],
            run_id="test-run"
        )

        reporter = EvidenceReporter(cases)
        md_path = tmp_path / "test.md"
        reporter.write_markdown(md_path)

        md_content = md_path.read_text(encoding="utf-8")

        # Executive summary table has Classification column
        assert "| Metric Dimension | Classification | Value | Notes |" in md_content
        assert "**Observed**" in md_content
        assert "**Diagnostic**" in md_content

    def test_jsonl_preserves_raw_schema_distinction(self, tmp_path: Path) -> None:
        """JSONL output must preserve the schema's field separation."""
        client = DummyClient()
        harness = EvidenceHarness(
            client=client,
            model="gpt-4o-mini",
            provider_name="openai",
        )

        cases = harness.run_all(
            [SimpleNamespace(
                id="test_case",
                category="test",
                messages=[{"role": "user", "content": "Hello world"}],
                expected_preserved=[],
            )],
            run_id="test-run"
        )

        reporter = EvidenceReporter(cases)
        jsonl_path = tmp_path / "test.jsonl"
        reporter.write_jsonl(jsonl_path)

        with open(jsonl_path, encoding="utf-8") as f:
            line = f.readline()
            data = json.loads(line)

        # Verify schema separation preserved in JSONL
        assert "baseline" in data
        assert "tokenopt" in data
        assert "provider_input_tokens" in data["baseline"]
        assert "provider_input_tokens" in data["tokenopt"]
        assert "estimated_original_tokens" in data["tokenopt"]
        assert "estimated_optimized_tokens" in data["tokenopt"]
        assert "estimated_tokens_saved" in data["tokenopt"]


class TestCP8SemanticSimilarityDiagnosticOnly:
    """Test that semantic similarity remains diagnostic-only and
    never affects validation/pass/fail."""

    def test_semantic_similarity_not_in_execution_status(self) -> None:
        """ExecutionStatus must not depend on semantic similarity."""
        client = DummyClient()
        harness = EvidenceHarness(
            client=client,
            model="gpt-4o-mini",
            provider_name="openai",
            enable_semantic_diagnostics=True,
        )

        cases = harness.run_all(
            [SimpleNamespace(
                id="test_case",
                category="test",
                messages=[{"role": "user", "content": "Hello world"}],
                expected_preserved=[],
            )],
            run_id="test-run"
        )

        rec = cases[0]
        # Execution status determined by provider errors, validation, task fidelity only
        assert rec.execution_status in (
            ExecutionStatus.SUCCESS,
            ExecutionStatus.BASELINE_PROVIDER_ERROR,
            ExecutionStatus.TOKENOPT_PROVIDER_ERROR,
            ExecutionStatus.VALIDATION_REJECT,
            ExecutionStatus.VALIDATION_ROLLBACK,
            ExecutionStatus.TASK_ASSERTION_FAILED,
        )
        # Semantic diagnostics present but separate
        assert rec.semantic_diagnostics.backend != "disabled"

    def test_semantic_similarity_does_not_affect_validation_decision(self) -> None:
        """Validation decision must come from ValidatorStage, not semantic similarity."""
        client = DummyClient()
        harness = EvidenceHarness(
            client=client,
            model="gpt-4o-mini",
            provider_name="openai",
            enable_semantic_diagnostics=True,
        )

        cases = harness.run_all(
            [SimpleNamespace(
                id="test_case",
                category="test",
                messages=[{"role": "user", "content": "Hello world"}],
                expected_preserved=[],
            )],
            run_id="test-run"
        )

        rec = cases[0]
        # Validation decision from preservation evidence (ValidatorStage)
        assert rec.preservation.validation_decision in ("accept", "reject")
        # Rollback from ValidatorStage
        assert isinstance(rec.preservation.rollback_applied, bool)
        # Semantic similarity is separate diagnostic
        assert rec.semantic_diagnostics.similarity_score is not None or \
               rec.semantic_diagnostics.backend.endswith("_error") or \
               rec.semantic_diagnostics.backend == "empty_text"

    def test_semantic_similarity_does_not_affect_task_fidelity(self) -> None:
        """Task fidelity must be determined by deterministic assertions, not semantic similarity."""
        client = DummyClient()
        harness = EvidenceHarness(
            client=client,
            model="gpt-4o-mini",
            provider_name="openai",
            enable_semantic_diagnostics=True,
        )

        cases = harness.run_all(
            [SimpleNamespace(
                id="case_02_instruction_heavy",
                category="test",
                messages=[{"role": "user", "content": "Test"}],
                expected_preserved=[],
            )],
            run_id="test-run"
        )

        rec = cases[0]
        # Task fidelity status from deterministic evaluator
        assert rec.task_fidelity.status in (
            TaskFidelityStatus.PASSED,
            TaskFidelityStatus.FAILED,
            TaskFidelityStatus.NOT_EVALUATED,
        )
        # Semantic similarity is separate
        assert hasattr(rec.semantic_diagnostics, "similarity_score")


class TestCP8ContextCaptureStageTelemetryOnly:
    """Verify _ContextCaptureStage is telemetry-only and does not mutate ctx.messages."""

    def test_context_capture_stage_does_not_mutate_messages(self) -> None:
        """_ContextCaptureStage must not modify ctx.messages content."""
        client = DummyClient()
        adapter = TokenOptAdapter(client)

        # Get the capture stage
        capture_stage = adapter._capture_stage
        assert isinstance(capture_stage, _ContextCaptureStage)

        # Create a context with messages
        original_messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
        ]
        ctx = OptimizationContext(
            messages=original_messages,
            model="gpt-4o-mini",
            config=client.config,
        )

        # Store original content
        original_content = ctx.messages[1]["content"]

        # Run the capture stage
        result_ctx = capture_stage.process(ctx)

        # Messages content must not be mutated
        assert result_ctx.messages[1]["content"] == original_content
        assert result_ctx.messages[0]["content"] == "You are helpful"

        # Capture stage only stores reference, doesn't modify
        assert capture_stage.last_context is result_ctx

    def test_context_capture_stage_reads_metrics_only(self) -> None:
        """_ContextCaptureStage must only read ctx.metrics, not write to it."""
        client = DummyClient()
        adapter = TokenOptAdapter(client)
        capture_stage = adapter._capture_stage

        ctx = OptimizationContext(
            messages=[{"role": "user", "content": "Test"}],
            model="gpt-4o-mini",
            config=client.config,
        )

        # Add some metrics
        ctx.metrics["test_metric"] = 42

        result_ctx = capture_stage.process(ctx)

        # Metrics should be unchanged
        assert result_ctx.metrics.get("test_metric") == 42
        # Capture stage should not add its own metrics
        assert "evidence_capture" not in result_ctx.metrics
        assert "capture_stage" not in result_ctx.metrics


class TestCP8ExtractProviderUsageSafe:
    """Test extract_provider_usage_safe behavior for CP8 compliance."""

    def test_zero_prompt_tokens_with_input_treated_as_none(self) -> None:
        """prompt_tokens == 0 with non-empty input must return None (untrustworthy)."""
        resp = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=0, completion_tokens=25, total_tokens=25)
        )
        in_t, out_t, tot_t = extract_provider_usage_safe(resp, has_input_messages=True)
        assert in_t is None
        assert out_t == 25
        assert tot_t is None  # Total also None when prompt is None

    def test_positive_prompt_tokens_preserved_intact(self) -> None:
        """Positive provider token counts must be preserved exactly."""
        resp = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=150, completion_tokens=42, total_tokens=192)
        )
        in_t, out_t, tot_t = extract_provider_usage_safe(resp, has_input_messages=True)
        assert in_t == 150
        assert out_t == 42
        assert tot_t == 192

    def test_missing_usage_returns_all_none(self) -> None:
        """Missing usage object must return (None, None, None)."""
        resp = SimpleNamespace(usage=None)
        in_t, out_t, tot_t = extract_provider_usage_safe(resp)
        assert in_t is None
        assert out_t is None
        assert tot_t is None

    def test_ollama_missing_prompt_eval_returns_none(self) -> None:
        """Ollama response missing prompt_eval_count must return None for input tokens."""
        resp_missing = {"eval_count": 35}
        in_t, out_t, tot_t = extract_provider_usage_safe(resp_missing, has_input_messages=True)
        assert in_t is None
        assert out_t == 35
        assert tot_t is None

    def test_anthropic_input_tokens_mapped_correctly(self) -> None:
        """Anthropic's input_tokens must map to provider_input_tokens."""
        resp = SimpleNamespace(
            usage=SimpleNamespace(input_tokens=30, output_tokens=10)
        )
        in_t, out_t, tot_t = extract_provider_usage_safe(resp)
        assert in_t == 30
        assert out_t == 10
        assert tot_t is None  # Provider did not supply total_tokens explicitly


    def test_explicit_provider_total_populated(self) -> None:
        """When provider explicitly supplies total_tokens, it must be preserved."""
        resp = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=40, completion_tokens=15, total_tokens=55)
        )
        in_t, out_t, tot_t = extract_provider_usage_safe(resp)
        assert in_t == 40
        assert out_t == 15
        assert tot_t == 55

    def test_missing_provider_total_with_input_output_is_none(self) -> None:
        """Missing provider total + input/output present → provider_total_tokens is None."""
        # OpenAI shape: prompt_tokens + completion_tokens but no total_tokens
        resp_openai = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=30, completion_tokens=10)
        )
        in_t, out_t, tot_t = extract_provider_usage_safe(resp_openai)
        assert in_t == 30
        assert out_t == 10
        assert tot_t is None

        # Anthropic shape: input_tokens + output_tokens but no total_tokens
        resp_anthropic = SimpleNamespace(
            usage=SimpleNamespace(input_tokens=30, output_tokens=10)
        )
        in_t2, out_t2, tot_t2 = extract_provider_usage_safe(resp_anthropic)
        assert in_t2 == 30
        assert out_t2 == 10
        assert tot_t2 is None

    def test_ollama_missing_total_eval_count_is_none(self) -> None:
        """Ollama-style usage with prompt_eval_count/eval_count but no total_eval_count → None."""
        resp_ollama = {"prompt_eval_count": 80, "eval_count": 35}
        in_t, out_t, tot_t = extract_provider_usage_safe(resp_ollama, has_input_messages=True)
        assert in_t == 80
        assert out_t == 35
        assert tot_t is None

    def test_provider_input_reduction_based_only_on_provider_input(self) -> None:
        """Provider input reduction must be based only on provider_input_tokens."""
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from tokenopt.clients.base import BaseOptimizedClient
        from tokenopt.config import get_prototype_config
        from tokenopt.evaluation.harness import EvidenceHarness

        class DummyClient(BaseOptimizedClient):
            def __init__(self):
                super().__init__(config=get_prototype_config())

            def _create_client(self):
                return MagicMock()

            def _call_api(self, messages, model, **kwargs):
                prompt_len = sum(len(str(m.get("content", "")).split()) for m in messages)
                return SimpleNamespace(
                    id="test",
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content="test", role="assistant")
                        )
                    ],
                    usage=SimpleNamespace(
                        prompt_tokens=prompt_len,
                        completion_tokens=10,
                        total_tokens=prompt_len + 10,
                    ),
                )

            def _extract_response_content(self, response):
                return response.choices[0].message.content

            def _extract_usage(self, response):
                return {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }

        client = DummyClient()
        harness = EvidenceHarness(client=client, model="gpt-4o-mini", provider_name="openai")

        case = SimpleNamespace(
            id="test", category="test",
            messages=[{"role": "user", "content": "Hello world"}],
            expected_preserved=[],
        )
        records = harness.run_all([case], run_id="test")
        rec = records[0]

        b_in = rec.baseline.provider_input_tokens
        t_in = rec.tokenopt.provider_input_tokens
        saved = rec.comparison.provider_tokens_saved

        assert saved is not None
        assert saved == b_in - t_in
        # The reduction formula uses provider_input_tokens (not estimated tokens,
        # not provider_total_tokens). Verified by equality above.


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
