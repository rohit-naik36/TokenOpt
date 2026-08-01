"""Regression tests: clarified per-request metrics (Post-M8 UAT).

Covers the UAT finding that ``compression_applied`` alone conflated "stage
executed" with "tokens actually reduced". The new fields
``compression_attempted`` / ``compression_effective`` / ``tokens_saved`` /
``reduction_percentage`` and the latency split (``model_latency_ms`` vs
``pipeline_latency_ms``) must be populated for every recorded request.
"""

import httpx

from tokenopt import OpenAI, TokenOptConfig
from tokenopt.config import RoutingRule
from tokenopt.observability import RequestMetrics


def _last(client: OpenAI) -> RequestMetrics:
    return client.metrics_collector.get_recent(1)[0]


def test_short_prompt_compression_attempted_but_not_effective(
    openai_transport: httpx.MockTransport,
) -> None:
    """A short prompt runs through the compressor unchanged: attempted, not effective."""
    client = OpenAI(
        api_key="test-key",
        http_client=httpx.Client(transport=openai_transport),
    )

    client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "hi there"}],
    )

    metric = _last(client)
    assert metric.compression_attempted is True
    assert metric.compression_effective is False
    assert metric.tokens_saved == 0
    assert metric.reduction_percentage == 0.0


def test_long_prompt_compression_effective(
    openai_transport: httpx.MockTransport,
) -> None:
    """A prompt over the compression budget is truncated: attempted and effective."""
    client = OpenAI(
        api_key="test-key",
        http_client=httpx.Client(transport=openai_transport),
    )
    long_prompt = "please kindly explain the difference between a router and a cache " * 100

    client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": long_prompt}],
    )

    metric = _last(client)
    assert metric.compression_attempted is True
    assert metric.compression_effective is True
    assert metric.tokens_saved > 0
    assert 0.0 < metric.reduction_percentage <= 100.0
    assert metric.optimized_tokens < metric.original_tokens


def test_latency_split_total_equals_model_plus_overhead(
    openai_transport: httpx.MockTransport,
) -> None:
    """Total latency is model inference plus TokenOpt pipeline overhead."""
    client = OpenAI(
        api_key="test-key",
        http_client=httpx.Client(transport=openai_transport),
    )

    client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "What is the weather?"}],
    )

    metric = _last(client)
    assert metric.pipeline_latency_ms > 0.0
    assert metric.model_latency_ms >= 0.0
    assert abs(metric.latency_ms - (metric.model_latency_ms + metric.pipeline_latency_ms)) < 1.0


def test_cache_hit_request_records_clarified_metrics(
    openai_transport: httpx.MockTransport,
) -> None:
    """Cache-hit requests still record the clarified fields."""
    client = OpenAI(
        api_key="test-key",
        http_client=httpx.Client(transport=openai_transport),
    )
    messages = [{"role": "user", "content": "cache me please"}]

    client.chat.completions.create(model="gpt-4o", messages=messages)
    client.chat.completions.create(model="gpt-4o", messages=messages)

    metric = _last(client)
    assert metric.cache_hit is True
    assert metric.compression_attempted is True
    assert isinstance(metric.tokens_saved, int)
    assert isinstance(metric.reduction_percentage, float)
    assert metric.model_latency_ms >= 0.0
    assert metric.pipeline_latency_ms >= 0.0


def test_disabled_compression_reports_not_attempted(
    openai_transport: httpx.MockTransport,
) -> None:
    """When compression is disabled, attempted/effective are both False."""
    client = OpenAI(
        config=TokenOptConfig(enable_compression=False, enable_routing=False),
        api_key="test-key",
        http_client=httpx.Client(transport=openai_transport),
    )

    client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "hi there"}],
    )

    metric = _last(client)
    assert metric.compression_attempted is False
    assert metric.compression_effective is False
    assert metric.tokens_saved == 0


def test_routing_reason_custom_rule_match(openai_transport: httpx.MockTransport) -> None:
    """A matching custom rule names the rule in routing_reason."""
    client = OpenAI(
        config=TokenOptConfig(
            routing_rules=[
                RoutingRule(
                    name="math_tasks",
                    condition=lambda q, m: "equation" in q.lower(),
                    model="o1-mini",
                    priority=40,
                )
            ],
        ),
        api_key="test-key",
        http_client=httpx.Client(transport=openai_transport),
    )

    client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Solve the equation x^2 = 49 for x."}],
    )

    metric = _last(client)
    assert metric.routing_applied is True
    assert metric.model == "o1-mini"
    assert metric.routing_reason == "math_tasks"


def test_routing_reason_complexity_fallback(
    openai_transport: httpx.MockTransport,
) -> None:
    """Without a rule match, routing_reason explains the complexity fallback."""
    client = OpenAI(
        config=TokenOptConfig(
            enable_routing=True,
            routing_rules=[],
            default_model="gpt-4o",
        ),
        api_key="test-key",
        http_client=httpx.Client(transport=openai_transport),
    )

    client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "What is the weather?"}],
    )

    metric = _last(client)
    assert metric.routing_applied is True
    assert metric.model == "gpt-4o-mini"
    assert metric.routing_reason == "complexity-based (low)"


def test_routing_disabled_reports_empty_reason(
    openai_transport: httpx.MockTransport,
) -> None:
    """When routing is disabled, routing_reason stays empty."""
    client = OpenAI(
        config=TokenOptConfig(enable_routing=False),
        api_key="test-key",
        http_client=httpx.Client(transport=openai_transport),
    )

    client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Solve the equation x^2 = 49 for x."}],
    )

    metric = _last(client)
    assert metric.routing_applied is False
    assert metric.routing_reason == ""
