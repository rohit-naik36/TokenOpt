"""Local model client wrapper for Ollama/vLLM/llama.cpp with TokenOpt optimization."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from tokenopt.clients._compat import _CompatShim
from tokenopt.clients.base import BaseOptimizedClient, _extract_openai_shape_usage
from tokenopt.config import RoutingRule, TokenOptConfig
from tokenopt.pipeline import OptimizationPipeline


class LocalClient(BaseOptimizedClient):
    """Client for local model servers (Ollama, vLLM, llama.cpp, LM Studio).

    The backend is auto-detected from the base URL:

    - ``http://localhost:11434`` (Ollama default) -> native ``ollama`` package
    - anything else -> OpenAI-compatible ``/v1`` endpoint (vLLM, llama.cpp, LM Studio)

    Local responses are normalized to the OpenAI chat format so the rest of the
    optimization pipeline (cache, metrics, cost estimation) works unchanged.
    """

    OLLAMA_DEFAULT_URL = "http://localhost:11434"

    def __init__(
        self,
        config: TokenOptConfig | None = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs: Any
    ):
        self.default_local_model = model or "llama3.1"
        super().__init__(
            config=config,
            api_key=api_key,
            base_url=base_url,
            **kwargs
        )

    def _detect_backend(self) -> str:
        """Detect backend from the base URL."""
        url = (self.base_url or self.OLLAMA_DEFAULT_URL).rstrip("/")
        if "11434" in url or "ollama" in url:
            return "ollama"
        return "openai"

    def _create_client(self) -> Any:
        if self._detect_backend() == "ollama":
            try:
                import ollama
            except ImportError as e:
                raise RuntimeError(
                    "The 'ollama' package is required for the Ollama backend "
                    "(base_url contains '11434' or 'ollama'). Install it with: "
                    "pip install tokenopt[local]"
                ) from e

            return ollama.Client(host=self.base_url or self.OLLAMA_DEFAULT_URL)

        # OpenAI-compatible server (vLLM, llama.cpp, LM Studio, etc.)
        from openai import OpenAI as OpenAIClient

        return OpenAIClient(
            api_key=self.api_key or "local-not-needed",
            base_url=self.base_url,
            **self.extra_kwargs
        )

    def _build_pipeline(
        self,
        routing_rule_filter: Callable[[RoutingRule], bool] | None = None,
    ) -> OptimizationPipeline:
        # The default router targets cloud models, so skip it for local servers.
        # Only keep custom routing rules that target local models (AND any
        # caller-supplied filter).
        def local_compatible(rule: RoutingRule) -> bool:
            return not self._is_cloud_model(rule.model) and (
                routing_rule_filter is None or routing_rule_filter(rule)
            )

        return super()._build_pipeline(routing_rule_filter=local_compatible)

    @staticmethod
    def _is_cloud_model(model: str) -> bool:
        return model.lower().startswith(("gpt-", "o1-", "o3-", "claude"))

    def _call_api(self, messages: list[dict], model: str, **kwargs: Any) -> Any:
        if self._detect_backend() == "ollama":
            return self._normalize_ollama_response(
                self._client.chat(
                    model=model,
                    messages=messages,
                    stream=kwargs.get("stream", False),
                    **{
                        k: kwargs[k]
                        for k in ("options", "format", "keep_alive", "template")
                        if k in kwargs
                    }
                )
            )

        return self._client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs
        )

    def _normalize_ollama_response(self, response: Any) -> SimpleNamespace:
        """Convert an Ollama response to the OpenAI chat completion shape."""
        def _get(obj: Any, key: str, default: Any = None) -> Any:
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        content = _get(_get(response, "message", {}), "content", "")
        prompt_tokens = _get(response, "prompt_eval_count", 0)
        completion_tokens = _get(response, "eval_count", 0)

        return SimpleNamespace(
            model=_get(response, "model", ""),
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content),
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
        return response.choices[0].message.content or ""

    def _extract_usage(self, response: Any) -> dict[str, int]:
        return _extract_openai_shape_usage(response)

    def chat_completion(
        self,
        messages: list[dict],
        model: str | None = None,
        model_explicit: bool | None = None,
        **kwargs: Any
    ) -> Any:
        """Chat completion defaulting to the configured local model."""
        explicit = model is not None if model_explicit is None else model_explicit
        return super().chat_completion(
            messages,
            model or self.default_local_model,
            model_explicit=explicit,
            **kwargs
        )

    # Compatibility: expose chat.completions interface
    @property
    def chat(self) -> Any:
        shim = _CompatShim(self)

        class Chat:
            completions = shim

        return Chat()


__all__ = ["LocalClient"]
