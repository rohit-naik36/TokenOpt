"""Evidence harness orchestrator for empirical baseline vs TokenOpt evaluation."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from tokenopt.clients.base import BaseOptimizedClient
from tokenopt.clients.local_client import LocalClient
from tokenopt.evaluation.adapters import (
    BaselineAdapter,
    BaselineExecutionResult,
    TokenOptAdapter,
    TokenOptExecutionResult,
    extract_effective_generation_parameters,
)
from tokenopt.evaluation.schema import (
    BaselineEvidence,
    ComparisonEvidence,
    EvidenceRecord,
    ExecutionStatus,
    PreservationEvidence,
    SemanticDiagnosticEvidence,
    TokenOptEvidence,
)
from tokenopt.evaluation.task_fidelity import evaluate_task_fidelity
from tokenopt.observability.metrics import estimate_cost
from tokenopt.utils.embeddings import (
    EmbeddingProvider,
    get_embedding_provider,
)


class EvidenceHarness:
    """Orchestrates paired empirical evaluation of Baseline vs TokenOpt."""

    def __init__(
        self,
        client: BaseOptimizedClient,
        model: str | None = None,
        provider_name: str = "generic",
        generation_parameters: dict[str, Any] | None = None,
        enable_semantic_diagnostics: bool = False,
    ):
        self.client = client
        self.model: str = model or str(getattr(client, "default_local_model", "gpt-4o-mini"))
        self.provider_name = provider_name
        self.generation_parameters = generation_parameters or {}
        self.enable_semantic_diagnostics = enable_semantic_diagnostics

        self.baseline_adapter = BaselineAdapter(self.client)
        self.tokenopt_adapter = TokenOptAdapter(self.client)

        self.effective_generation_parameters = extract_effective_generation_parameters(
            self.client,
            self.model,
            self.generation_parameters,
            self.provider_name,
        )

        self._embedding_provider = (
            get_embedding_provider() if enable_semantic_diagnostics else None
        )

    def _determine_execution_environment(self) -> str:
        """Distinguish local compute (e.g. Ollama) from cloud API services."""
        if isinstance(self.client, LocalClient):
            return "local_compute"
        if self.provider_name.lower() in ("ollama", "local", "vllm", "llama.cpp"):
            return "local_compute"
        if self.model.lower().startswith(("llama", "mistral", "phi", "qwen")):
            return "local_compute"
        return "cloud_api"

    def run_case(
        self,
        case: Any,
        run_id: str,
    ) -> EvidenceRecord:
        """Run a single evaluation case under both Baseline and TokenOpt."""
        timestamp = datetime.now(timezone.utc).isoformat()
        exec_env = self._determine_execution_environment()
        messages = deepcopy(case.messages)
        kwargs = dict(self.generation_parameters)

        baseline_res: BaselineExecutionResult | None = None
        tokenopt_res: TokenOptExecutionResult | None = None
        exec_status = ExecutionStatus.SUCCESS
        err_msg: str | None = None

        # 1. Execute Baseline
        try:
            baseline_res = self.baseline_adapter.execute(
                messages=messages,
                model=self.model,
                **kwargs,
            )
        except Exception as exc:
            exec_status = ExecutionStatus.BASELINE_PROVIDER_ERROR
            err_msg = f"Baseline error: {exc}"

        # 2. Execute TokenOpt
        try:
            tokenopt_res = self.tokenopt_adapter.execute(
                messages=messages,
                model=self.model,
                **kwargs,
            )
        except Exception as exc:
            if exec_status == ExecutionStatus.SUCCESS:
                exec_status = ExecutionStatus.TOKENOPT_PROVIDER_ERROR
                err_msg = f"TokenOpt error: {exc}"
            else:
                err_msg = f"{err_msg} | TokenOpt error: {exc}"

        # 3. Evaluate Status & Preservation
        if tokenopt_res is not None:
            if tokenopt_res.rollback_applied:
                exec_status = ExecutionStatus.VALIDATION_ROLLBACK
            elif tokenopt_res.validation_decision == "reject":
                exec_status = ExecutionStatus.VALIDATION_REJECT

        # 4. Construct Evidence Components
        # Baseline Evidence
        b_in = baseline_res.provider_input_tokens if baseline_res else None
        b_out = baseline_res.provider_output_tokens if baseline_res else None
        b_tot = baseline_res.provider_total_tokens if baseline_res else None
        b_lat = baseline_res.total_latency_ms if baseline_res else None
        b_text = baseline_res.completion_text if baseline_res else ""

        if exec_env == "local_compute":
            b_cost: float | None = 0.0
        elif b_in is not None and b_out is not None:
            b_cost = estimate_cost(self.model, b_in, b_out)
        else:
            b_cost = None

        baseline_evidence = BaselineEvidence(
            provider_input_tokens=b_in,
            provider_output_tokens=b_out,
            provider_total_tokens=b_tot,
            total_latency_ms=b_lat,
            projected_cost=b_cost,
            completion_text=b_text,
        )

        # TokenOpt Evidence
        t_in = tokenopt_res.provider_input_tokens if tokenopt_res else None
        t_out = tokenopt_res.provider_output_tokens if tokenopt_res else None
        t_tot = tokenopt_res.provider_total_tokens if tokenopt_res else None
        t_lat = tokenopt_res.total_latency_ms if tokenopt_res else None
        t_pipe = tokenopt_res.pipeline_latency_ms if tokenopt_res else None
        t_mod = tokenopt_res.model_latency_ms if tokenopt_res else None
        t_text = tokenopt_res.completion_text if tokenopt_res else ""
        t_orig_est = tokenopt_res.estimated_original_tokens if tokenopt_res else 0
        t_opt_est = tokenopt_res.estimated_optimized_tokens if tokenopt_res else 0
        t_saved_est = tokenopt_res.estimated_tokens_saved if tokenopt_res else 0

        if exec_env == "local_compute":
            t_cost: float | None = 0.0
        elif t_in is not None and t_out is not None:
            t_cost = estimate_cost(self.model, t_in, t_out)
        else:
            t_cost = None

        tokenopt_evidence = TokenOptEvidence(
            estimated_original_tokens=t_orig_est,
            estimated_optimized_tokens=t_opt_est,
            estimated_tokens_saved=t_saved_est,
            provider_input_tokens=t_in,
            provider_output_tokens=t_out,
            provider_total_tokens=t_tot,
            total_latency_ms=t_lat,
            pipeline_latency_ms=t_pipe,
            model_latency_ms=t_mod,
            projected_cost=t_cost,
            completion_text=t_text,
        )

        # Preservation Evidence
        preservation_evidence = PreservationEvidence(
            validation_decision=tokenopt_res.validation_decision if tokenopt_res else "unknown",
            rollback_applied=tokenopt_res.rollback_applied if tokenopt_res else False,
            rollback_reason=tokenopt_res.rollback_reason if tokenopt_res else None,
            rollback_violations=tokenopt_res.rollback_violations if tokenopt_res else [],
            invariants_checked=tokenopt_res.invariants_checked if tokenopt_res else 0,
            invariants_passed=tokenopt_res.invariants_passed if tokenopt_res else 0,
            invariants_failed=tokenopt_res.invariants_failed if tokenopt_res else 0,
        )

        # Task Fidelity Evidence
        task_fidelity = evaluate_task_fidelity(case.id, b_text, t_text)

        # Semantic Diagnostic Evidence
        sem_diag = self._evaluate_semantic_similarity(b_text, t_text)

        # Comparison Evidence
        provider_tokens_saved: int | None = None
        provider_reduction_pct: float | None = None
        if b_in is not None and t_in is not None:
            provider_tokens_saved = b_in - t_in
            if b_in > 0:
                provider_reduction_pct = round((provider_tokens_saved / b_in) * 100.0, 2)
            else:
                provider_reduction_pct = 0.0

        projected_cost_saved: float | None = None
        if b_cost is not None and t_cost is not None:
            projected_cost_saved = round(b_cost - t_cost, 6)

        comparison_evidence = ComparisonEvidence(
            provider_tokens_saved=provider_tokens_saved,
            provider_reduction_pct=provider_reduction_pct,
            projected_cost_saved=projected_cost_saved,
            pipeline_overhead_ms=t_pipe,
            total_latency_delta_ms=round(t_lat - b_lat, 2) if t_lat and b_lat else None,
        )

        return EvidenceRecord(
            run_id=run_id,
            case_id=case.id,
            category=case.category,
            timestamp=timestamp,
            provider=self.provider_name,
            model=self.model,
            execution_environment=exec_env,
            generation_parameters=kwargs,
            requested_generation_parameters=kwargs,
            effective_generation_parameters=self.effective_generation_parameters,
            execution_status=exec_status,
            error_message=err_msg,
            baseline=baseline_evidence,
            tokenopt=tokenopt_evidence,
            preservation=preservation_evidence,
            task_fidelity=task_fidelity,
            semantic_diagnostics=sem_diag,
            comparison=comparison_evidence,
        )

    def _evaluate_semantic_similarity(
        self,
        baseline_text: str,
        tokenopt_text: str,
    ) -> SemanticDiagnosticEvidence:
        """Compute diagnostic semantic similarity without using it for pass/fail."""
        if not self.enable_semantic_diagnostics or self._embedding_provider is None:
            return SemanticDiagnosticEvidence(backend="disabled", similarity_score=None)

        if not baseline_text.strip() or not tokenopt_text.strip():
            return SemanticDiagnosticEvidence(backend="empty_text", similarity_score=0.0)

        backend_name = (
            "sentence-transformers"
            if isinstance(self._embedding_provider, EmbeddingProvider)
            else "exact_hash_fallback"
        )

        try:
            emb1 = self._embedding_provider.embed_single(baseline_text)
            emb2 = self._embedding_provider.embed_single(tokenopt_text)
            score = float(self._embedding_provider.similarity(emb1, emb2))
            return SemanticDiagnosticEvidence(
                backend=backend_name,
                similarity_score=round(score, 4),
            )
        except Exception:
            return SemanticDiagnosticEvidence(
                backend=f"{backend_name}_error",
                similarity_score=None,
            )

    def run_all(
        self,
        cases: Sequence[Any],
        run_id: str | None = None,
    ) -> list[EvidenceRecord]:
        """Execute paired evaluation across all provided cases."""
        active_run_id = run_id or f"run-{uuid.uuid4().hex[:12]}"
        records: list[EvidenceRecord] = []
        for case in cases:
            rec = self.run_case(case, active_run_id)
            records.append(rec)
        return records
