"""Execution adapters for Baseline and TokenOpt pipelines."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from tokenopt.clients.base import BaseOptimizedClient
from tokenopt.clients.local_client import LocalClient
from tokenopt.config import get_prototype_config
from tokenopt.pipeline.base import OptimizationContext, PipelineStage


def extract_provider_usage_safe(
    response: Any,
    has_input_messages: bool | list[Any] = True,
) -> tuple[int | None, int | None, int | None]:
    """Extract provider-reported usage strictly preserving None if unavailable.

    Args:
        response: Provider API response object or dictionary.
        has_input_messages: Either a boolean flag indicating non-empty input,
            or the message list itself. Defaults to True.

    Returns:
        tuple of (input_tokens, output_tokens, total_tokens).
        Returns None for any quantity not genuinely provided by the provider.
        When prompt_tokens is reported as 0 and has_input_messages is True,
        prompt_tokens is treated as None (untrustworthy/unreported).
    """
    if response is None:
        return None, None, None

    has_input = (
        bool(has_input_messages)
        if isinstance(has_input_messages, (bool, list))
        else True
    )

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    # 1. Standard OpenAI shape: response.usage
    usage_obj = getattr(response, "usage", None)
    if usage_obj is not None:
        prompt_tokens = getattr(usage_obj, "prompt_tokens", None)
        if prompt_tokens is None:
            prompt_tokens = getattr(usage_obj, "input_tokens", None)

        completion_tokens = getattr(usage_obj, "completion_tokens", None)
        if completion_tokens is None:
            completion_tokens = getattr(usage_obj, "output_tokens", None)

        total_tokens = getattr(usage_obj, "total_tokens", None)

    # 2. Dictionary usage representation
    elif isinstance(response, dict) and "usage" in response and response["usage"]:
        u = response["usage"]
        prompt_tokens = u.get("prompt_tokens")
        if prompt_tokens is None:
            prompt_tokens = u.get("input_tokens")

        completion_tokens = u.get("completion_tokens")
        if completion_tokens is None:
            completion_tokens = u.get("output_tokens")

        total_tokens = u.get("total_tokens")

    # 3. Direct Ollama dictionary keys
    elif (
        isinstance(response, dict)
        and ("prompt_eval_count" in response or "eval_count" in response)
    ):
        prompt_tokens = response.get("prompt_eval_count")
        completion_tokens = response.get("eval_count")
        total_tokens = response.get("total_eval_count")

    # 4. Direct Ollama object attributes
    elif hasattr(response, "prompt_eval_count") or hasattr(response, "eval_count"):
        prompt_tokens = getattr(response, "prompt_eval_count", None)
        completion_tokens = getattr(response, "eval_count", None)
        total_tokens = getattr(response, "total_eval_count", None)

    else:
        return None, None, None

    # Untrustworthy 0 prompt tokens when input messages exist
    if has_input and prompt_tokens == 0:
        prompt_tokens = None

    # Derive total_tokens if not directly provided
    if prompt_tokens is None:
        # Prompt tokens unknown; total tokens cannot be fully determined
        total_tokens = None
    elif total_tokens is None:
        if completion_tokens is not None:
            total_tokens = prompt_tokens + completion_tokens
    elif has_input and total_tokens == 0:
        total_tokens = None

    return prompt_tokens, completion_tokens, total_tokens


@dataclass
class BaselineExecutionResult:
    """Raw result from executing baseline directly against the provider."""

    completion_text: str
    provider_input_tokens: int | None
    provider_output_tokens: int | None
    provider_total_tokens: int | None
    total_latency_ms: float
    raw_response: Any


class BaselineAdapter:
    """Executes requests directly against the underlying provider, bypassing TokenOpt."""

    def __init__(self, client: BaseOptimizedClient):
        self.client = client

    def execute(
        self,
        messages: list[dict[str, Any]],
        model: str,
        **kwargs: Any,
    ) -> BaselineExecutionResult:
        """Call underlying provider directly, bypassing pipeline.run()."""
        start = perf_counter()

        # Call underlying provider API directly via client's native _call_api
        response = self.client._call_api(messages=messages, model=model, **kwargs)

        elapsed_ms = (perf_counter() - start) * 1000.0

        content = self.client._extract_response_content(response)
        in_tok, out_tok, tot_tok = extract_provider_usage_safe(
            response,
            has_input_messages=bool(messages),
        )

        return BaselineExecutionResult(
            completion_text=content,
            provider_input_tokens=in_tok,
            provider_output_tokens=out_tok,
            provider_total_tokens=tot_tok,
            total_latency_ms=elapsed_ms,
            raw_response=response,
        )


class _ContextCaptureStage(PipelineStage):
    """Internal non-mutating stage to observe OptimizationContext without altering pipeline."""

    name = "evidence_capture"

    def __init__(self) -> None:
        super().__init__()
        self.last_context: OptimizationContext | None = None

    def process(self, ctx: OptimizationContext) -> OptimizationContext:
        self.last_context = ctx
        return ctx


@dataclass
class TokenOptExecutionResult:
    """Result from executing through canonical TokenOpt optimization pipeline."""

    completion_text: str
    estimated_original_tokens: int
    estimated_optimized_tokens: int
    estimated_tokens_saved: int
    provider_input_tokens: int | None
    provider_output_tokens: int | None
    provider_total_tokens: int | None
    total_latency_ms: float
    pipeline_latency_ms: float
    model_latency_ms: float
    validation_decision: str
    rollback_applied: bool
    rollback_reason: str | None
    rollback_violations: list[dict[str, Any]]
    invariants_checked: int
    invariants_passed: int
    invariants_failed: int
    raw_response: Any


class TokenOptAdapter:
    """Executes requests through TokenOpt pipeline configured for Prototype v0.1 boundary."""

    def __init__(self, client: BaseOptimizedClient):
        self.client = client
        # 1. Enforce prototype configuration
        self.client.config = get_prototype_config()
        # 2. Synchronize pipeline configuration
        self.client.pipeline.config = self.client.config

        # 3. Insert _ContextCaptureStage immediately AFTER ValidatorStage
        self.client.pipeline.stages = [
            s for s in self.client.pipeline.stages if not isinstance(s, _ContextCaptureStage)
        ]
        self._capture_stage = _ContextCaptureStage()
        validator_index = next(
            (
                i
                for i, s in enumerate(self.client.pipeline.stages)
                if getattr(s, "name", None) == "validator"
            ),
            None,
        )
        if validator_index is not None:
            self.client.pipeline.stages.insert(validator_index + 1, self._capture_stage)
        else:
            self.client.pipeline.stages.append(self._capture_stage)

    def execute(
        self,
        messages: list[dict[str, Any]],
        model: str,
        **kwargs: Any,
    ) -> TokenOptExecutionResult:
        """Execute chat completion through canonical TokenOpt pipeline."""
        # Reset capture state at the very beginning of execution
        self._capture_stage.last_context = None

        start = perf_counter()

        response = self.client.chat_completion(
            messages=messages,
            model=model,
            **kwargs,
        )

        elapsed_ms = (perf_counter() - start) * 1000.0

        content = self.client._extract_response_content(response)
        in_tok, out_tok, tot_tok = extract_provider_usage_safe(
            response,
            has_input_messages=bool(messages),
        )

        # Retrieve metrics recorded by client
        recent = self.client.metrics_collector.get_recent(1)
        req_metrics = recent[0] if recent else None

        # Retrieve captured context telemetry
        ctx = self._capture_stage.last_context
        ctx_metrics: dict[str, Any] = ctx.metrics if ctx is not None else {}

        orig_tokens = (
            req_metrics.original_tokens
            if req_metrics
            else (ctx.original_token_count if ctx else 0)
        )
        opt_tokens = (
            req_metrics.optimized_tokens
            if req_metrics
            else ctx_metrics.get("optimized_token_count", orig_tokens)
        )
        tokens_saved = (
            req_metrics.tokens_saved
            if req_metrics
            else ctx_metrics.get("tokens_saved", orig_tokens - opt_tokens)
        )

        pipeline_latency = (
            req_metrics.pipeline_latency_ms
            if req_metrics
            else ctx_metrics.get("pipeline_latency_ms", 0.0)
        )
        model_latency = (
            req_metrics.model_latency_ms
            if req_metrics
            else max(0.0, elapsed_ms - pipeline_latency)
        )

        val_decision = (
            req_metrics.validation_decision
            if req_metrics and req_metrics.validation_decision
            else ctx_metrics.get("validation_decision", "unknown")
        )
        rollback = (
            req_metrics.rollback_applied
            if req_metrics
            else ctx_metrics.get("rollback_applied", False)
        )

        return TokenOptExecutionResult(
            completion_text=content,
            estimated_original_tokens=orig_tokens,
            estimated_optimized_tokens=opt_tokens,
            estimated_tokens_saved=tokens_saved,
            provider_input_tokens=in_tok,
            provider_output_tokens=out_tok,
            provider_total_tokens=tot_tok,
            total_latency_ms=elapsed_ms,
            pipeline_latency_ms=pipeline_latency,
            model_latency_ms=model_latency,
            validation_decision=val_decision,
            rollback_applied=rollback,
            rollback_reason=ctx_metrics.get("rollback_reason"),
            rollback_violations=ctx_metrics.get("rollback_violations", []),
            invariants_checked=ctx_metrics.get("validation_invariants_checked", 0),
            invariants_passed=ctx_metrics.get("validation_invariants_passed", 0),
            invariants_failed=ctx_metrics.get("validation_invariants_failed", 0),
            raw_response=response,
        )


def extract_effective_generation_parameters(
    client: Any,
    model: str,
    requested_parameters: dict[str, Any] | None = None,
    provider_name: str | None = None,
) -> dict[str, Any] | None:
    """Extract effective provider/model parameters for telemetry and reproducibility.

    For Ollama: inspects model metadata via client._client.show(model) if available,
    combining known Ollama runtime sampling defaults with model-specific directives
    (e.g. stop sequences) and caller-requested overrides.

    For other providers (or when metadata is unavailable): returns None to avoid
    inventing hypothetical defaults.
    """
    if (
        "effective_generation_parameters" in getattr(client, "__dict__", {})
        and client.__dict__["effective_generation_parameters"] is not None
    ):
        return dict(client.__dict__["effective_generation_parameters"])

    req = dict(requested_parameters or {})

    # Detect if backend is Ollama
    is_ollama = False
    ollama_client = None

    if provider_name is not None:
        if provider_name.lower() == "ollama":
            is_ollama = True
            ollama_client = getattr(client, "_client", None)
    elif isinstance(client, LocalClient):
        if client._detect_backend() == "ollama":
            is_ollama = True
            ollama_client = getattr(client, "_client", None)
    elif "_detect_backend" in type(client).__dict__:
        try:
            if client._detect_backend() == "ollama":
                is_ollama = True
                ollama_client = getattr(client, "_client", None)
        except Exception:
            pass
    elif hasattr(type(client), "_normalize_ollama_response"):
        is_ollama = True
        ollama_client = getattr(client, "_client", None)

    if not is_ollama or ollama_client is None:
        return None

    if not hasattr(ollama_client, "show") or not callable(ollama_client.show):
        return None

    try:
        info = ollama_client.show(model)
    except Exception:
        # Probe failed or raised: do NOT fabricate defaults
        return None

    if info is None:
        return None

    raw_params = getattr(info, "parameters", None)
    if not raw_params or not isinstance(raw_params, str) or not raw_params.strip():
        # Missing, non-string, or empty parameters: cannot establish effective values
        return None

    parsed_params: dict[str, Any] = {}
    stops: list[str] = []
    lines = raw_params.strip().splitlines()
    parsed_valid_line = False

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(None, 1)
        if len(parts) != 2:
            # Malformed line structure
            return None
        k, v = parts[0].strip().lower(), parts[1].strip()
        if k == "stop":
            if (v.startswith('"') and v.endswith('"')) or (
                v.startswith("'") and v.endswith("'")
            ):
                v = v[1:-1]
            stops.append(v)
            parsed_valid_line = True
        elif k in ("temperature", "top_p"):
            try:
                parsed_params[k] = float(v)
                parsed_valid_line = True
            except ValueError:
                # Malformed numeric value
                return None
        elif k in ("top_k", "num_ctx", "num_predict", "seed"):
            try:
                parsed_params[k] = int(v)
                parsed_valid_line = True
            except ValueError:
                # Malformed numeric value
                return None
        else:
            parsed_params[k] = v
            parsed_valid_line = True

    if not parsed_valid_line:
        return None

    if stops:
        parsed_params["stop"] = stops

    # Since the probe succeeded and model parameters are established, apply
    # Ollama's documented server runtime defaults for any unspecified sampling parameters
    effective: dict[str, Any] = {
        "temperature": parsed_params.get("temperature", 0.8),
        "top_p": parsed_params.get("top_p", 0.9),
        "top_k": parsed_params.get("top_k", 40),
    }

    # Include any other Modelfile parameters that were parsed
    for k, v in parsed_params.items():
        if k not in effective:
            effective[k] = v

    # Overlay any caller-requested parameters without mutating caller's dict
    for k, v in req.items():
        if k == "options" and isinstance(v, dict):
            effective.update(v)
        else:
            effective[k] = v

    return effective
