"""TokenOpt SDK - drop-in token and prompt optimization for LLM clients.

Usage:
    from tokenopt import OpenAI, TokenOptConfig

    client = OpenAI(config=TokenOptConfig())
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Long prompt..."}],
    )
"""

from tokenopt.clients import Anthropic, BaseOptimizedClient, LocalClient, OpenAI
from tokenopt.config import RoutingRule, TokenOptConfig, get_default_config
from tokenopt.factory import create_client, create_client_from_model, detect_provider
from tokenopt.observability import MetricsCollector, RequestMetrics, estimate_cost
from tokenopt.utils import count_message_tokens, count_tokens, truncate_to_tokens

__version__ = "0.1.0"

__all__ = [
    "TokenOptConfig",
    "RoutingRule",
    "get_default_config",
    "BaseOptimizedClient",
    "OpenAI",
    "Anthropic",
    "LocalClient",
    "create_client",
    "create_client_from_model",
    "detect_provider",
    "MetricsCollector",
    "RequestMetrics",
    "estimate_cost",
    "count_tokens",
    "count_message_tokens",
    "truncate_to_tokens",
]
