"""Comprehensive unit tests for TokenOpt Prototype v0.2 Evidence Harness."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from evaluation.cases import get_cases
from tokenopt.clients.base import BaseOptimizedClient
from tokenopt.config import get_prototype_config
from tokenopt.evaluation.adapters import (
    BaselineAdapter,
    TokenOptAdapter,
    extract_effective_generation_parameters,
    extract_provider_usage_safe,
)
from tokenopt.evaluation.harness import EvidenceHarness
from tokenopt.evaluation.reporters import EvidenceReporter
from tokenopt.evaluation.schema import (
    BaselineEvidence,
    ComparisonEvidence,
    EvidenceRecord,
    ExecutionStatus,
    PreservationEvidence,
    SemanticDiagnosticEvidence,
    TaskFidelityEvidence,
    TaskFidelityStatus,
    TokenOptEvidence,
)
from tokenopt.evaluation.task_fidelity import evaluate_task_fidelity


class DummyClient(BaseOptimizedClient):
    """Stub client for testing adapters without live LLM calls."""

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


class TestEvidenceSchema:
    """Test schema and data contract serialization."""

    def test_evidence_record_serialization(self) -> None:
        rec = EvidenceRecord(
            run_id="run-test-1",
            case_id="case_01",
            category="simple_conversation",
            timestamp="2026-09-25T12:00:00Z",
            provider="ollama",
            model="llama3.1",
            execution_environment="local_compute",
            generation_parameters={"temperature": 0.0},
            execution_status=ExecutionStatus.SUCCESS,
            baseline=BaselineEvidence(
                provider_input_tokens=50,
                provider_output_tokens=20,
                provider_total_tokens=70,
                total_latency_ms=100.0,
                projected_cost=0.0,
                completion_text="Hello",
            ),
            tokenopt=TokenOptEvidence(
                estimated_original_tokens=55,
                estimated_optimized_tokens=45,
                estimated_tokens_saved=10,
                provider_input_tokens=42,
                provider_output_tokens=20,
                provider_total_tokens=62,
                total_latency_ms=90.0,
                pipeline_latency_ms=1.5,
                model_latency_ms=88.5,
                projected_cost=0.0,
                completion_text="Hello",
            ),
            preservation=PreservationEvidence(
                validation_decision="accept",
                rollback_applied=False,
                invariants_checked=6,
                invariants_passed=6,
                invariants_failed=0,
            ),
            task_fidelity=TaskFidelityEvidence(
                status=TaskFidelityStatus.NOT_EVALUATED,
                details="Open-ended",
            ),
            semantic_diagnostics=SemanticDiagnosticEvidence(
                backend="disabled",
            ),
            comparison=ComparisonEvidence(
                provider_tokens_saved=8,
                provider_reduction_pct=16.0,
                projected_cost_saved=0.0,
                pipeline_overhead_ms=1.5,
                total_latency_delta_ms=-10.0,
            ),
        )

        d = rec.to_dict()
        assert d["run_id"] == "run-test-1"
        assert d["execution_status"] == "success"
        assert d["baseline"]["provider_input_tokens"] == 50
        assert d["tokenopt"]["estimated_tokens_saved"] == 10
        assert d["comparison"]["provider_tokens_saved"] == 8
        assert d["task_fidelity"]["status"] == "not_evaluated"

        # Verify round-trip JSON serialization
        serialized = json.dumps(d)
        deserialized = json.loads(serialized)
        assert deserialized["run_id"] == "run-test-1"


class TestUsageExtraction:
    """Test extract_provider_usage_safe handling of present and missing usage."""

    def test_extract_openai_shape_present(self) -> None:
        resp = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=40, completion_tokens=15, total_tokens=55)
        )
        in_t, out_t, tot_t = extract_provider_usage_safe(resp)
        assert in_t == 40
        assert out_t == 15
        assert tot_t == 55

    def test_extract_anthropic_shape_present(self) -> None:
        resp = SimpleNamespace(
            usage=SimpleNamespace(input_tokens=30, output_tokens=10)
        )
        in_t, out_t, tot_t = extract_provider_usage_safe(resp)
        assert in_t == 30
        assert out_t == 10
        assert tot_t == 40

    def test_extract_usage_missing_returns_none(self) -> None:
        resp = SimpleNamespace(usage=None)
        in_t, out_t, tot_t = extract_provider_usage_safe(resp)
        assert in_t is None
        assert out_t is None
        assert tot_t is None

    def test_extract_usage_none_response(self) -> None:
        in_t, out_t, tot_t = extract_provider_usage_safe(None)
        assert in_t is None
        assert out_t is None
        assert tot_t is None

    def test_zero_prompt_tokens_treated_as_none_with_input(self) -> None:
        """Verify prompt_tokens == 0 with non-empty input is treated as None."""
        resp = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=0, completion_tokens=25, total_tokens=25)
        )
        # With boolean flag
        in_t, out_t, tot_t = extract_provider_usage_safe(resp, has_input_messages=True)
        assert in_t is None
        assert out_t == 25
        assert tot_t is None

        # With input message list
        in_t2, out_t2, tot_t2 = extract_provider_usage_safe(
            resp,
            has_input_messages=[{"role": "user", "content": "hello"}],
        )
        assert in_t2 is None
        assert out_t2 == 25
        assert tot_t2 is None

        # With has_input_messages=False (empty input list)
        in_t3, out_t3, tot_t3 = extract_provider_usage_safe(resp, has_input_messages=False)
        assert in_t3 == 0
        assert out_t3 == 25
        assert tot_t3 == 25

    def test_positive_tokens_preserved_intact(self) -> None:
        """Verify positive provider token counts are preserved intact."""
        resp = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=150, completion_tokens=42, total_tokens=192)
        )
        in_t, out_t, tot_t = extract_provider_usage_safe(resp, has_input_messages=True)
        assert in_t == 150
        assert out_t == 42
        assert tot_t == 192

    def test_ollama_shape_missing_prompt_eval_count_no_false_zero(self) -> None:
        """Verify missing prompt_eval_count does not produce false zero token count."""
        # Missing prompt_eval_count
        resp_missing = {"eval_count": 35}
        in_t, out_t, tot_t = extract_provider_usage_safe(resp_missing, has_input_messages=True)
        assert in_t is None
        assert out_t == 35
        assert tot_t is None

        # prompt_eval_count == 0 on non-empty input
        resp_zero = {"prompt_eval_count": 0, "eval_count": 35}
        in_t0, out_t0, tot_t0 = extract_provider_usage_safe(resp_zero, has_input_messages=True)
        assert in_t0 is None
        assert out_t0 == 35
        assert tot_t0 is None

        # Positive prompt_eval_count
        resp_positive = {"prompt_eval_count": 80, "eval_count": 35}
        in_tp, out_tp, tot_tp = extract_provider_usage_safe(resp_positive, has_input_messages=True)
        assert in_tp == 80
        assert out_tp == 35
        assert tot_tp == 115


class TestBaselineAdapter:
    """Test that BaselineAdapter genuinely bypasses TokenOpt pipeline.run()."""

    def test_baseline_bypasses_pipeline(self) -> None:
        client = DummyClient()
        # Mock pipeline.run to ensure it is never invoked
        client.pipeline.run = MagicMock(
            side_effect=AssertionError("pipeline.run must NOT be called")
        )

        adapter = BaselineAdapter(client)
        messages = [{"role": "user", "content": "Test baseline query"}]

        result = adapter.execute(messages=messages, model="gpt-4o-mini")

        assert result.completion_text != ""
        assert client.pipeline.run.call_count == 0
        assert result.provider_input_tokens is not None
        assert result.total_latency_ms >= 0.0


class TestTokenOptAdapter:
    """Test that TokenOptAdapter executes through canonical pipeline and captures telemetry."""

    def test_tokenopt_adapter_captures_telemetry(self) -> None:
        client = DummyClient()
        adapter = TokenOptAdapter(client)

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Please kindly tell me the weather today."},
        ]

        result = adapter.execute(messages=messages, model="gpt-4o-mini")

        assert result.completion_text != ""
        assert result.estimated_original_tokens > 0
        assert result.validation_decision in ("accept", "reject")
        assert result.rollback_applied is False
        assert result.total_latency_ms >= 0.0

    def test_config_sync(self) -> None:
        """Verify client.config and client.pipeline.config reference the same prototype config."""
        client = DummyClient()
        TokenOptAdapter(client)

        proto_cfg = get_prototype_config()
        assert client.config.enable_compression == proto_cfg.enable_compression
        assert client.config.cache_enabled == proto_cfg.cache_enabled
        assert client.config.enable_routing == proto_cfg.enable_routing
        assert client.pipeline.config is client.config

    def test_stage_placement(self) -> None:
        """Verify _capture_stage is located at validator_index + 1."""
        client = DummyClient()
        adapter = TokenOptAdapter(client)

        stage_names = [getattr(s, "name", type(s).__name__) for s in client.pipeline.stages]
        assert "validator" in stage_names
        val_idx = stage_names.index("validator")
        capture_idx = client.pipeline.stages.index(adapter._capture_stage)
        assert capture_idx == val_idx + 1
        assert client.pipeline.stages[capture_idx].name == "evidence_capture"

    def test_state_reset_on_error(self) -> None:
        """Verify _capture_stage.last_context is None on error and cannot retain context."""
        from tokenopt.pipeline.base import OptimizationContext

        client = DummyClient()
        adapter = TokenOptAdapter(client)

        # Pre-seed last_context with a stale context
        stale_ctx = OptimizationContext(
            messages=[{"role": "user", "content": "stale content"}],
            model="gpt-4o-mini",
            config=client.config,
        )
        adapter._capture_stage.last_context = stale_ctx

        # Simulate provider failure during chat_completion
        client.chat_completion = MagicMock(
            side_effect=RuntimeError("Provider API connection failed")
        )

        with pytest.raises(RuntimeError, match="Provider API connection failed"):
            adapter.execute(
                messages=[{"role": "user", "content": "new question"}],
                model="gpt-4o-mini",
            )

        # Context must have been reset to None at execute start and cannot be stale
        assert adapter._capture_stage.last_context is None


class TestTaskFidelityEvaluators:
    """Test deterministic assertions for qualified cases and NOT_EVALUATED for others."""

    def test_case_02_directives(self) -> None:
        passing = "[EXEC-SUMMARY]\n- Item 1\n- Item 2\n- Item 3\nStrict Level-4 compliance."
        evidence = evaluate_task_fidelity("case_02_instruction_heavy", passing, passing)
        assert evidence.status == TaskFidelityStatus.PASSED
        assert evidence.tokenopt_passed is True

        failing = "Summary with no bullets and no level tag."
        evidence_fail = evaluate_task_fidelity("case_02_instruction_heavy", passing, failing)
        assert evidence_fail.status == TaskFidelityStatus.FAILED
        assert evidence_fail.tokenopt_passed is False

    def test_case_05_contract_date_iso_and_natural_representations(self) -> None:
        """Verify case_05 accepts ISO and equivalent natural-language date representations."""
        # ISO date representation
        iso_text = "Delivery confirmed for Phase-2 on 2026-01-15."
        ev_iso = evaluate_task_fidelity("case_05_date_constraints", iso_text, iso_text)
        assert ev_iso.status == TaskFidelityStatus.PASSED
        assert ev_iso.tokenopt_passed is True

        # Natural language equivalent: 'January 15, 2026'
        nat_text = "The launch window for Phase-2 has been confirmed for January 15, 2026."
        ev_nat = evaluate_task_fidelity("case_05_date_constraints", nat_text, nat_text)
        assert ev_nat.status == TaskFidelityStatus.PASSED
        assert ev_nat.tokenopt_passed is True

        # Natural language equivalent: '15 January 2026'
        nat_text2 = "Phase-2 delivery is scheduled for 15 January 2026."
        ev_nat2 = evaluate_task_fidelity("case_05_date_constraints", nat_text2, nat_text2)
        assert ev_nat2.status == TaskFidelityStatus.PASSED

    def test_case_05_contract_date_rejects_incorrect_date(self) -> None:
        """Verify case_05 rejects incorrect dates or missing phase."""
        passing = "Delivery confirmed for Phase-2 on 2026-01-15."

        # Incorrect day
        wrong_day = "Delivery confirmed for Phase-2 on 2026-01-16."
        ev1 = evaluate_task_fidelity("case_05_date_constraints", passing, wrong_day)
        assert ev1.status == TaskFidelityStatus.FAILED
        assert ev1.tokenopt_passed is False

        # Incorrect natural month/day
        wrong_nat = "Delivery confirmed for Phase-2 on January 20, 2026."
        ev2 = evaluate_task_fidelity("case_05_date_constraints", passing, wrong_nat)
        assert ev2.status == TaskFidelityStatus.FAILED
        assert ev2.tokenopt_passed is False

        # Vague date
        vague = "Delivery confirmed for Phase-2 next month."
        ev3 = evaluate_task_fidelity("case_05_date_constraints", passing, vague)
        assert ev3.status == TaskFidelityStatus.FAILED

        # Missing Phase-2
        missing_phase = "Delivery confirmed on 2026-01-15."
        ev4 = evaluate_task_fidelity("case_05_date_constraints", passing, missing_phase)
        assert ev4.status == TaskFidelityStatus.FAILED

    def test_case_07_node_count(self) -> None:
        passing = "The node_count parameter is set to 12."
        evidence = evaluate_task_fidelity("case_07_json", passing, passing)
        assert evidence.status == TaskFidelityStatus.PASSED

        failing = "The node count could not be determined."
        evidence_fail = evaluate_task_fidelity("case_07_json", passing, failing)
        assert evidence_fail.status == TaskFidelityStatus.FAILED

    def test_case_08_sla_breach(self) -> None:
        passing = "EU-Central suffered an SLA Breach."
        evidence = evaluate_task_fidelity("case_08_markdown_table", passing, passing)
        assert evidence.status == TaskFidelityStatus.PASSED

        failing = "US-East suffered an SLA Breach."
        evidence_fail = evaluate_task_fidelity("case_08_markdown_table", passing, failing)
        assert evidence_fail.status == TaskFidelityStatus.FAILED

    def test_case_09_rag_incident(self) -> None:
        passing = "A Sev-1 alert must be sent to security-ops@acme.corp within 15 minutes."
        evidence = evaluate_task_fidelity("case_09_rag_context", passing, passing)
        assert evidence.status == TaskFidelityStatus.PASSED

        failing = "Alert must be dispatched as soon as possible."
        evidence_fail = evaluate_task_fidelity("case_09_rag_context", passing, failing)
        assert evidence_fail.status == TaskFidelityStatus.FAILED

    def test_case_11_fatal_panic(self) -> None:
        passing = "Node-99 experienced fatal panic: KERN-ERR-0x89AB."
        evidence = evaluate_task_fidelity("case_11_truncation_risk", passing, passing)
        assert evidence.status == TaskFidelityStatus.PASSED

        failing = "System operating within normal parameters."
        evidence_fail = evaluate_task_fidelity("case_11_truncation_risk", passing, failing)
        assert evidence_fail.status == TaskFidelityStatus.FAILED

        non_eval_cases = [
            "case_01_simple_conversation",
            "case_03_system_user",
            "case_04_numeric_constraints",
            "case_06_code",
            "case_10_repetitive_context",
            "case_12_minimal_compression",
        ]
        for cid in non_eval_cases:
            evidence = evaluate_task_fidelity(cid, "any text", "any text")
            assert evidence.status == TaskFidelityStatus.NOT_EVALUATED
            assert evidence.baseline_passed is None
            assert evidence.tokenopt_passed is None


class TestHarnessOrchestrator:
    """Test paired execution, parameter preservation, failure handling, and token accounting."""

    def test_parameter_preservation(self) -> None:
        client = DummyClient()
        harness = EvidenceHarness(
            client=client,
            model="gpt-4o-mini",
            provider_name="openai",
            generation_parameters={"temperature": 0.35, "max_tokens": 500},
        )

        cases = get_cases()[:1]
        records = harness.run_all(cases, run_id="run-param-test")
        assert len(records) == 1
        assert records[0].generation_parameters == {"temperature": 0.35, "max_tokens": 500}

    def test_token_accounting_missing_usage(self) -> None:
        client = DummyClient(usage_available=False)
        harness = EvidenceHarness(
            client=client,
            model="gpt-4o-mini",
            provider_name="openai",
        )

        cases = get_cases()[:1]
        records = harness.run_all(cases, run_id="run-missing-usage")
        assert len(records) == 1
        rec = records[0]

        # Provider tokens must be None, NOT zero
        assert rec.baseline.provider_input_tokens is None
        assert rec.tokenopt.provider_input_tokens is None
        assert rec.comparison.provider_tokens_saved is None
        assert rec.comparison.provider_reduction_pct is None

        # Local estimates must remain distinct
        assert rec.tokenopt.estimated_original_tokens > 0

    def test_local_compute_pricing(self) -> None:
        client = DummyClient(usage_available=True)
        harness = EvidenceHarness(
            client=client,
            model="llama3.1",
            provider_name="ollama",
        )

        cases = get_cases()[:1]
        records = harness.run_all(cases, run_id="run-local-compute")
        assert len(records) == 1
        rec = records[0]

        assert rec.execution_environment == "local_compute"
        assert rec.baseline.projected_cost == 0.0
        assert rec.tokenopt.projected_cost == 0.0
        assert rec.comparison.projected_cost_saved == 0.0

    def test_baseline_error_handling(self) -> None:
        client = DummyClient()
        client._call_api = MagicMock(side_effect=RuntimeError("Provider connection failed"))

        harness = EvidenceHarness(
            client=client,
            model="gpt-4o-mini",
            provider_name="openai",
        )

        cases = get_cases()[:1]
        records = harness.run_all(cases, run_id="run-err-test")
        assert len(records) == 1
        rec = records[0]

        assert rec.execution_status == ExecutionStatus.BASELINE_PROVIDER_ERROR
        assert "Provider connection failed" in (rec.error_message or "")


class TestReporters:
    """Test JSONL, CSV, and Markdown exports."""

    def test_reporters_generate_files(self, tmp_path: Path) -> None:
        client = DummyClient(usage_available=True)
        harness = EvidenceHarness(
            client=client,
            model="gpt-4o-mini",
            provider_name="openai",
        )

        cases = get_cases()[:2]
        records = harness.run_all(cases, run_id="run-report-test")

        reporter = EvidenceReporter(records)

        jsonl_path = tmp_path / "test.jsonl"
        csv_path = tmp_path / "test.csv"
        md_path = tmp_path / "test.md"

        reporter.write_jsonl(jsonl_path)
        reporter.write_csv(csv_path)
        reporter.write_markdown(md_path)

        # Verify JSONL
        with open(jsonl_path, encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) == 2
            json.loads(lines[0])

        # Verify CSV
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 2
            assert "base_in_tokens" in rows[0]
            assert "cost_saved_proj" in rows[0]

        # Verify Markdown content
        md_content = md_path.read_text(encoding="utf-8")
        assert "# TokenOpt Prototype v0.2: Empirical Evidence Report" in md_content
        assert "Observed" in md_content
        assert "Projected" in md_content
        assert "Case-by-Case Comparison Table" in md_content


class TestFull12CaseMockExecution:
    """Run all 12 cases through mock execution end-to-end."""

    def test_execute_all_12_cases(self, tmp_path: Path) -> None:
        from evaluation.run_evidence import MockEvidenceClient

        client = MockEvidenceClient(model="llama3.1")
        harness = EvidenceHarness(
            client=client,
            model="llama3.1",
            provider_name="mock",
        )

        cases = get_cases()
        assert len(cases) == 12

        records = harness.run_all(cases, run_id="run-12-test")
        assert len(records) == 12

        # Verify all 12 cases executed successfully
        for r in records:
            assert r.execution_status == ExecutionStatus.SUCCESS
            assert r.preservation.validation_decision == "accept"
            assert r.preservation.rollback_applied is False

        # Verify task fidelity distribution
        evaluated = [
            r for r in records
            if r.task_fidelity.status != TaskFidelityStatus.NOT_EVALUATED
        ]
        not_evaluated = [
            r for r in records
            if r.task_fidelity.status == TaskFidelityStatus.NOT_EVALUATED
        ]

        assert len(evaluated) == 6
        assert len(not_evaluated) == 6

        # Check export
        reporter = EvidenceReporter(records)
        json_path = tmp_path / "all_12.json"
        reporter.write_json(json_path)
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
            assert len(data) == 12


class TestEvaluationFixtures:
    """Verify evaluation fixtures meet turn structure and preservation requirements."""

    def test_case_05_ends_with_user_turn(self) -> None:
        """Verify case_05 ends with a user request and retains Phase-2 and date."""
        cases = {c.id: c for c in get_cases()}
        c5 = cases["case_05_date_constraints"]
        assert c5.messages[-1]["role"] == "user"
        content = c5.messages[-1]["content"]
        assert "Phase-2" in content
        assert "2026-01-15" in content

    def test_case_10_ends_with_user_turn(self) -> None:
        """Verify case_10 ends with a user turn containing all required entities."""
        cases = {c.id: c for c in get_cases()}
        c10 = cases["case_10_repetitive_context"]
        assert c10.messages[-1]["role"] == "user"
        content = c10.messages[-1]["content"]
        assert "AUTH-TOKEN-XY99" in content
        assert "enforce_strict_validation=true" in content
        assert "production" in content

    def test_case_10_deterministic_requirements_intact(self) -> None:
        """Verify case_10 preservation markers and detected invariants remain intact."""
        from tokenopt.pipeline.analyzer import ContextAnalyzer

        cases = {c.id: c for c in get_cases()}
        c10 = cases["case_10_repetitive_context"]
        markers = {m.marker for m in c10.expected_preserved}
        assert "AUTH-TOKEN-XY99" in markers
        assert "enforce_strict_validation=true" in markers

        pmap = ContextAnalyzer().analyze(c10.messages)
        u1_invs = {inv.marker for inv in pmap.get_invariants_for_message(1)}
        assert "AUTH-TOKEN-XY99" in u1_invs
        assert "enforce_strict_validation=true" in u1_invs


class DummyOllamaClient(DummyClient):
    """Stub Ollama client with mock show() metadata."""

    def __init__(self, raw_parameters: str | None = None, raise_error: bool = False):
        super().__init__(model="llama3.1")
        self.raw_parameters = raw_parameters
        self.raise_error = raise_error
        mock_ollama = MagicMock()
        if raise_error:
            mock_ollama.show.side_effect = RuntimeError("Ollama daemon unreachable")
        else:
            mock_ollama.show.return_value = SimpleNamespace(parameters=self.raw_parameters)
        self._client = mock_ollama

    def _detect_backend(self) -> str:
        return "ollama"


class TestEffectiveGenerationParameters:
    """Tests for requested vs effective generation parameters telemetry."""

    def test_requested_parameters_unchanged_and_recorded(self) -> None:
        client = DummyClient()
        harness = EvidenceHarness(
            client=client,
            model="gpt-4o-mini",
            provider_name="openai",
            generation_parameters={"temperature": 0.35, "max_tokens": 500},
        )
        cases = get_cases()[:1]
        records = harness.run_all(cases, run_id="run-param-requested")
        assert len(records) == 1
        rec = records[0]

        # Both legacy generation_parameters and requested_generation_parameters must match
        assert rec.generation_parameters == {"temperature": 0.35, "max_tokens": 500}
        assert rec.requested_generation_parameters == {"temperature": 0.35, "max_tokens": 500}

    def test_effective_parameters_recorded_separately(self) -> None:
        client = DummyOllamaClient(
            raw_parameters='stop "<|start_header_id|>"\nstop "<|eot_id|>"\ntemperature 0.7'
        )
        harness = EvidenceHarness(
            client=client,
            model="llama3.1",
            provider_name="ollama",
            generation_parameters={"max_tokens": 256},
        )
        cases = get_cases()[:1]
        records = harness.run_all(cases, run_id="run-param-effective")
        rec = records[0]

        # Requested must reflect ONLY what was requested
        assert rec.requested_generation_parameters == {"max_tokens": 256}

        # Effective must reflect provider defaults + model modelfile + requested overlay
        assert rec.effective_generation_parameters is not None
        assert rec.effective_generation_parameters["temperature"] == 0.7
        assert rec.effective_generation_parameters["top_p"] == 0.9
        assert rec.effective_generation_parameters["top_k"] == 40
        assert rec.effective_generation_parameters["max_tokens"] == 256
        assert rec.effective_generation_parameters["stop"] == [
            "<|start_header_id|>",
            "<|eot_id|>",
        ]

        # Test direct function extraction
        direct_extracted = extract_effective_generation_parameters(
            client, "llama3.1", {"max_tokens": 256}, "ollama"
        )
        assert direct_extracted == rec.effective_generation_parameters

    def test_missing_or_unavailable_effective_parameters_do_not_cause_failure(self) -> None:
        # Standard cloud client does not expose effective sampling defaults
        client = DummyClient()
        harness = EvidenceHarness(
            client=client,
            model="gpt-4o-mini",
            provider_name="openai",
        )
        cases = get_cases()[:1]
        records = harness.run_all(cases, run_id="run-cloud-no-effective")
        assert records[0].effective_generation_parameters is None

        # Failing Ollama show() call returns None rather than fabricating defaults
        failing_ollama = DummyOllamaClient(raise_error=True)
        harness_ollama = EvidenceHarness(
            client=failing_ollama,
            model="llama3.1",
            provider_name="ollama",
        )
        records_ollama = harness_ollama.run_all(cases, run_id="run-ollama-fallback")
        assert records_ollama[0].effective_generation_parameters is None

    def test_malformed_or_incomplete_metadata_returns_none(self) -> None:
        """Verify malformed or incomplete metadata returns None and does not fabricate defaults."""
        cases = get_cases()[:1]

        # Case A: empty parameters string
        empty_params_client = DummyOllamaClient(raw_parameters="")
        h_empty = EvidenceHarness(
            client=empty_params_client,
            model="llama3.1",
            provider_name="ollama",
        )
        recs_empty = h_empty.run_all(cases, run_id="run-empty-meta")
        assert recs_empty[0].effective_generation_parameters is None

        # Case B: None parameters
        none_params_client = DummyOllamaClient(raw_parameters=None)
        h_none = EvidenceHarness(
            client=none_params_client,
            model="llama3.1",
            provider_name="ollama",
        )
        recs_none = h_none.run_all(cases, run_id="run-none-meta")
        assert recs_none[0].effective_generation_parameters is None

        # Case C: malformed syntax (missing value)
        malformed_syntax = DummyOllamaClient(raw_parameters="temperature_without_value")
        h_syntax = EvidenceHarness(
            client=malformed_syntax,
            model="llama3.1",
            provider_name="ollama",
        )
        recs_syntax = h_syntax.run_all(cases, run_id="run-bad-syntax")
        assert recs_syntax[0].effective_generation_parameters is None

        # Case D: malformed numeric value (non-float temperature)
        malformed_num = DummyOllamaClient(raw_parameters="temperature not_a_float")
        h_num = EvidenceHarness(
            client=malformed_num,
            model="llama3.1",
            provider_name="ollama",
        )
        recs_num = h_num.run_all(cases, run_id="run-bad-num")
        assert recs_num[0].effective_generation_parameters is None

    def test_no_generation_parameter_silently_changed(self) -> None:
        """Verify that provider calls receive ONLY requested parameters, not effective defaults."""
        client = DummyOllamaClient(raw_parameters='temperature 0.7')
        client._call_api = MagicMock(return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Test", role="assistant"))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        ))
        harness = EvidenceHarness(
            client=client,
            model="llama3.1",
            provider_name="ollama",
            generation_parameters={"max_tokens": 100},
        )
        cases = get_cases()[:1]
        harness.run_all(cases, run_id="run-verify-no-silent-params")

        # Inspect kwargs passed to _call_api: must contain max_tokens=100 and NOT temperature=0.7
        for call_args in client._call_api.call_args_list:
            kwargs = call_args.kwargs
            assert kwargs.get("max_tokens") == 100
            assert "temperature" not in kwargs

    def test_reporters_render_generation_parameters(self, tmp_path: Path) -> None:
        client = DummyOllamaClient(raw_parameters='temperature 0.7\nstop "<|eot_id|>"')
        harness = EvidenceHarness(
            client=client,
            model="llama3.1",
            provider_name="ollama",
            generation_parameters={"temperature": 0.5},
        )
        cases = get_cases()[:1]
        records = harness.run_all(cases, run_id="run-reporter-params")

        reporter = EvidenceReporter(records)
        csv_file = tmp_path / "params.csv"
        md_file = tmp_path / "params.md"
        reporter.write_csv(csv_file)
        reporter.write_markdown(md_file)

        # Verify CSV has columns and content
        with open(csv_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 1
            assert "requested_params" in rows[0]
            assert "effective_params" in rows[0]
            assert "0.5" in rows[0]["requested_params"]
            assert "0.5" in rows[0]["effective_params"]

        # Verify Markdown contains the configuration block
        md_content = md_file.read_text(encoding="utf-8")
        assert "### Generation Parameters Configuration" in md_content
        assert "**Requested Parameters:**" in md_content
        assert "**Effective Parameters (Provider/Model Defaults):**" in md_content
        assert "<|eot_id|>" in md_content
