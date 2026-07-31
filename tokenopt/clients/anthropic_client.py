"""Anthropic client wrapper with TokenOpt optimization."""

from __future__ import annotations

from typing import Any

from anthropic import Anthropic as AnthropicClient

from tokenopt.clients.base import BaseOptimizedClient


class Anthropic(BaseOptimizedClient):
    """Drop-in replacement for anthropic.Anthropic with token optimization."""

    def _create_client(self) -> AnthropicClient:
        return AnthropicClient(
            api_key=self.api_key,
            base_url=self.base_url,
            **self.extra_kwargs
        )

    def _call_api(self, messages: list[dict], model: str, **kwargs) -> Any:
        # Convert messages format for Anthropic
        system = None
        anthropic_messages = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "system":
                system = content
            elif role in ("user", "assistant"):
                anthropic_messages.append({"role": role, "content": content})

        return self._client.messages.create(
            model=model,
            messages=anthropic_messages,
            system=system,
            max_tokens=kwargs.get("max_tokens", 4096),
            **{k: v for k, v in kwargs.items() if k not in ("max_tokens",)}
        )

    def _extract_response_content(self, response: Any) -> str:
        if response.content:
            return "".join(block.text for block in response.content if hasattr(block, "text"))
        return ""

    def _extract_usage(self, response: Any) -> dict[str, int]:
        if response.usage:
            return {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            }
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # Compatibility: expose messages interface
    @property
    def messages(self) -> Any:
        class Messages:
            def __init__(self, outer):
                self._outer = outer

            def create(self, messages, model=None, **kwargs):
                return self._outer.chat_completion(messages, model, **kwargs)

        return Messages(self)


__all__ = ["Anthropic"]
