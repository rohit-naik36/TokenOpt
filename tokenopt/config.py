"""Configuration for TokenOpt SDK."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


class RoutingRule(BaseModel):
    """Rule for model routing based on query characteristics."""

    name: str
    condition: Callable[[str, list[dict]], bool]  # (query, messages) -> bool
    model: str
    priority: int = 0


@dataclass
class TokenOptConfig:
    """Main configuration for TokenOpt optimization pipeline.

    Attributes:
        compression_ratio: Target compression ratio (0.0-1.0). 0.5 = 50% reduction.
        enable_compression: Whether to enable prompt compression.
        cache_enabled: Whether to enable semantic caching.
        cache_ttl: Cache time-to-live in seconds.
        cache_similarity_threshold: Similarity threshold for cache hits (0.0-1.0).
        cache_max_size: Maximum number of cached entries (in-memory).
        redis_url: Optional Redis URL for distributed caching.
        enable_routing: Whether to enable model routing.
        routing_rules: Custom routing rules (evaluated in priority order).
        default_model: Default model if no routing rule matches.
        enable_summarization: Whether to summarize conversation history.
        summarization_threshold: Token count threshold to trigger summarization.
        summarization_model: Model to use for summarization.
        rag_max_chunks: Maximum RAG chunks after optimization.
        rag_similarity_threshold: Minimum similarity for RAG chunk retention.
        fewshot_max_examples: Maximum few-shot examples to include.
        fewshot_selection_strategy: Strategy for few-shot selection
            ("similarity", "diversity", "random").
        observability_enabled: Whether to collect metrics.
        metrics_callback: Optional callback for custom metrics handling.
    """

    # Compression
    compression_ratio: float = 0.5
    enable_compression: bool = True

    # Caching
    cache_enabled: bool = True
    cache_ttl: int = 3600
    cache_similarity_threshold: float = 0.95
    cache_max_size: int = 10000
    redis_url: str | None = None

    # Routing
    enable_routing: bool = True
    routing_rules: list[RoutingRule] = field(default_factory=list)
    default_model: str = "gpt-4o-mini"

    # Summarization
    enable_summarization: bool = True
    summarization_threshold: int = 8000
    summarization_model: str = "gpt-4o-mini"

    # RAG Optimization
    rag_max_chunks: int = 5
    rag_similarity_threshold: float = 0.7

    # Few-shot Optimization
    fewshot_max_examples: int = 3
    fewshot_selection_strategy: str = "similarity"

    # Observability
    observability_enabled: bool = True
    metrics_callback: Callable[[dict[str, Any]], None] | None = None

    def __post_init__(self) -> None:
        if not 0 < self.compression_ratio <= 1:
            raise ValueError("compression_ratio must be in (0, 1]")
        if not 0 < self.cache_similarity_threshold <= 1:
            raise ValueError("cache_similarity_threshold must be in (0, 1]")
        if not 0 < self.rag_similarity_threshold <= 1:
            raise ValueError("rag_similarity_threshold must be in (0, 1]")


def get_default_config() -> TokenOptConfig:
    """Get default configuration with sensible routing rules."""
    return TokenOptConfig(
        routing_rules=[
            RoutingRule(
                name="simple_queries",
                condition=lambda q, m: len(q.split()) < 20 and not any(
                    k in q.lower() for k in ["analyze", "compare", "detailed", "comprehensive"]
                ),
                model="gpt-4o-mini",
                priority=10,
            ),
            RoutingRule(
                name="code_tasks",
                condition=lambda q, m: any(
                    k in q.lower()
                    for k in ["code", "function", "debug", "refactor", "implement"]
                ),
                model="gpt-4o",
                priority=20,
            ),
            RoutingRule(
                name="reasoning_tasks",
                condition=lambda q, m: any(
                    k in q.lower() for k in ["reason", "step by step", "think", "logic", "proof"]
                ),
                model="o1-mini",
                priority=30,
            ),
        ]
    )
