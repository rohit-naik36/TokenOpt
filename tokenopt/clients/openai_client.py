"""OpenAI client wrapper with TokenOpt optimization."""

from __future__ import annotations

from typing import Any

from openai import OpenAI as OpenAIClient

from tokenopt.clients.base import BaseOptimizedClient


class OpenAI(BaseOptimizedClient):
    """Drop-in replacement for openai.OpenAI with token optimization."""

    def _create_client(self) -> OpenAIClient:
        return OpenAIClient(
            api_key=self.api_key,
            base_url=self.base_url,
            **self.extra_kwargs
        )

    def _call_api(self, messages: list[dict], model: str, **kwargs) -> Any:
        return self._client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs
        )

    def _extract_response_content(self, response: Any) -> str:
        return response.choices[0].message.content or ""

    def _extract_usage(self, response: Any) -> dict[str, int]:
        if response.usage:
            return {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # Compatibility: expose chat.completions interface
    @property
    def chat(self) -> Any:
        class ChatCompletions:
            def __init__(self, outer):
                self._outer = outer

            def create(self, messages, model=None, **kwargs):
                return self._outer.chat_completion(messages, model, **kwargs)

        return ChatCompletions(self)


# For direct import compatibility
__all__ = ["OpenAI"]
