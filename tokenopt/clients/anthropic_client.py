"""Anthropic client wrapper with TokenOpt optimization."""

from __future__ import annotations

from typing import Any

from anthropic import Anthropic as AnthropicClient

from tokenopt.clients.base import BaseOptimizedClient
from tokenopt.pipeline import OptimizationPipeline, RouterStage


class Anthropic(BaseOptimizedClient):
    """Drop-in replacement for anthropic.Anthropic with token optimization."""

    def _create_client(self) -> AnthropicClient:
        return AnthropicClient(
            api_key=self.api_key,
            base_url=self.base_url,
            **self.extra_kwargs
        )

    def _build_pipeline(self) -> OptimizationPipeline:
        # The default router targets OpenAI models (gpt-*); routing an
        # Anthropic request to a gpt model would break the API call, so only
        # keep custom rules that target Anthropic models.
        stages = [s for s in super()._build_pipeline().stages if s.name != "router"]
        claude_rules = [r for r in self.config.routing_rules if "claude" in r.model.lower()]
        if claude_rules:
            from dataclasses import replace

            router_config = replace(self.config, routing_rules=claude_rules)
            stages.insert(0, RouterStage(router_config))
        return OptimizationPipeline(stages, self.config)

    def _call_api(self, messages: list[dict], model: str, **kwargs: Any) -> Any:
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
            def __init__(self, outer: Any):
                self._outer = outer

            def create(
                self,
                messages: list[dict[str, Any]],
                model: str | None = None,
                **kwargs: Any
            ) -> Any:
                return self._outer.chat_completion(messages, model, **kwargs)

        return Messages(self)


__all__ = ["Anthropic"]
