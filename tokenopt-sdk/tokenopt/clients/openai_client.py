"""OpenAI client wrapper with TokenOpt optimization."""

from __future__ import annotations

from typing import Any

from openai import OpenAI as OpenAIClient

from tokenopt.clients._compat import _CompatShim
from tokenopt.clients.base import BaseOptimizedClient, _extract_openai_shape_usage


class OpenAI(BaseOptimizedClient):
    """Drop-in replacement for openai.OpenAI with token optimization."""

    def _create_client(self) -> OpenAIClient:
        return OpenAIClient(
            api_key=self.api_key,
            base_url=self.base_url,
            **self.extra_kwargs
        )

    def _call_api(self, messages: list[dict], model: str, **kwargs: Any) -> Any:
        return self._client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs
        )

    def _extract_response_content(self, response: Any) -> str:
        return response.choices[0].message.content or ""

    def _extract_usage(self, response: Any) -> dict[str, int]:
        return _extract_openai_shape_usage(response)

    # Compatibility: expose chat.completions interface
    @property
    def chat(self) -> Any:
        shim = _CompatShim(self)

        class Chat:
            completions = shim

        return Chat()


# For direct import compatibility
__all__ = ["OpenAI"]
