"""Client factory for unified multi-model access."""

from __future__ import annotations

from typing import Any

from tokenopt.clients import Anthropic, BaseOptimizedClient, LocalClient, OpenAI
from tokenopt.config import TokenOptConfig


def detect_provider(model: str | None = None, base_url: str | None = None) -> str:
    """Detect provider from model name or base URL.

    Returns one of "openai", "anthropic", or "local".
    """
    if base_url and "11434" in base_url:
        return "local"
    if model:
        model_lower = model.lower()
        if model_lower.startswith(("gpt-", "o1-", "o3-", "gpt", "text-")):
            return "openai"
        if "claude" in model_lower:
            return "anthropic"
        return "local"
    return "openai"


def create_client(
    provider: str = "auto",
    model: str | None = None,
    config: TokenOptConfig | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    **kwargs: Any
) -> BaseOptimizedClient:
    """Create an optimized client for the given provider or model.

    Args:
        provider: "auto", "openai", "anthropic", or "local".
        model: Model name (also used to auto-detect provider and as default).
        config: Optional TokenOptConfig.
        api_key: API key for cloud providers.
        base_url: Custom endpoint (e.g. local server URL).
    """
    if provider == "auto":
        provider = detect_provider(model, base_url)

    if config is None and model:
        config = TokenOptConfig(default_model=model)

    if provider == "openai":
        return OpenAI(config=config, api_key=api_key, base_url=base_url, **kwargs)
    if provider == "anthropic":
        return Anthropic(config=config, api_key=api_key, base_url=base_url, **kwargs)
    if provider == "local":
        return LocalClient(
            config=config,
            model=model,
            api_key=api_key,
            base_url=base_url,
            **kwargs
        )
    raise ValueError(
        f"Unknown provider: {provider!r}. Use 'openai', 'anthropic', 'local', or 'auto'."
    )


def create_client_from_model(model: str, **kwargs: Any) -> BaseOptimizedClient:
    """Create a client by auto-detecting the provider from the model name."""
    return create_client(provider="auto", model=model, **kwargs)


__all__ = ["create_client", "create_client_from_model", "detect_provider"]
