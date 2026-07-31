"""Integration tests: Anthropic adapter end-to-end flow with stubbed HTTP.

Every test injects ``httpx.MockTransport`` into the underlying anthropic SDK
via the ``http_client=`` keyword, so no network traffic ever occurs. The
transport records request bodies so tests can assert what was actually sent.
"""

from __future__ import annotations

import anthropic
import httpx
import pytest

from tokenopt import Anthropic, RoutingRule, TokenOptConfig, get_default_config


def test_drop_in_messages_full_flow(
    anthropic_client: Anthropic, anthropic_requests: list
) -> None:
    response = anthropic_client.messages.create(
        model="claude-3-5-sonnet",
        max_tokens=100,
        messages=[{"role": "user", "content": "Hello"}],
    )

    assert response.content[0].text == "mock reply"
    assert len(anthropic_requests) == 1
    body = anthropic_requests[0]
    assert body["model"] == "claude-3-5-sonnet"
    assert body["messages"] == [{"role": "user", "content": "Hello"}]
    assert body["max_tokens"] == 100

    summary = anthropic_client.get_metrics_summary()
    assert summary["total_requests"] == 1
    assert summary["error_rate"] == 0.0
    assert summary["optimization_usage"]["routing"] == 0


def test_system_message_forwarded_separately(
    anthropic_client: Anthropic, anthropic_requests: list
) -> None:
    anthropic_client.messages.create(
        model="claude-3-5-sonnet",
        messages=[
            {"role": "system", "content": "You are a concise poet."},
            {"role": "user", "content": "Write a haiku"},
            {"role": "assistant", "content": "Autumn leaves falling"},
            {"role": "user", "content": "Now another one"},
        ],
    )

    body = anthropic_requests[0]
    assert body["system"] == "You are a concise poet."
    assert body["messages"] == [
        {"role": "user", "content": "Write a haiku"},
        {"role": "assistant", "content": "Autumn leaves falling"},
        {"role": "user", "content": "Now another one"},
    ]
    assert body["max_tokens"] == 4096


def test_default_routing_rules_filtered_for_anthropic(
    anthropic_transport: httpx.MockTransport, anthropic_requests: list
) -> None:
    """Default gpt-targeted routing rules must not rewrite Anthropic models."""
    client = Anthropic(
        config=get_default_config(),
        api_key="test-key",
        http_client=httpx.Client(transport=anthropic_transport),
    )

    client.messages.create(
        model="claude-3-5-sonnet",
        messages=[{"role": "user", "content": "What is the weather?"}],
    )

    assert anthropic_requests[0]["model"] == "claude-3-5-sonnet"


def test_custom_claude_routing_rule_applied(
    anthropic_transport: httpx.MockTransport, anthropic_requests: list
) -> None:
    config = TokenOptConfig(
        routing_rules=[
            RoutingRule(
                name="claude_haiku",
                condition=lambda q, m: "hello" in q.lower(),
                model="claude-3-5-haiku",
                priority=10,
            )
        ]
    )
    client = Anthropic(
        config=config,
        api_key="test-key",
        http_client=httpx.Client(transport=anthropic_transport),
    )

    client.messages.create(
        model="claude-3-5-sonnet",
        messages=[{"role": "user", "content": "hello there"}],
    )

    assert anthropic_requests[0]["model"] == "claude-3-5-haiku"


def test_identical_second_call_hits_cache(
    anthropic_client: Anthropic, anthropic_requests: list
) -> None:
    messages = [{"role": "user", "content": "Hello"}]

    first = anthropic_client.messages.create(
        model="claude-3-5-sonnet", messages=messages
    )
    second = anthropic_client.messages.create(
        model="claude-3-5-sonnet", messages=messages
    )

    assert first.content[0].text == second.content[0].text
    assert len(anthropic_requests) == 1
    summary = anthropic_client.get_metrics_summary()
    assert summary["total_requests"] == 2
    assert summary["cache_hit_rate"] == 0.5


def test_provider_error_reraises_and_records_metrics(
    error_transport: httpx.MockTransport,
) -> None:
    client = Anthropic(
        config=TokenOptConfig(),
        api_key="test-key",
        http_client=httpx.Client(transport=error_transport),
    )

    with pytest.raises(anthropic.APIStatusError):
        client.messages.create(
            model="claude-3-5-sonnet",
            messages=[{"role": "user", "content": "Hello"}],
        )

    summary = client.get_metrics_summary()
    assert summary["total_requests"] == 1
    assert summary["error_rate"] == 1.0
    assert "500" in client.metrics_collector.get_recent(1)[0].error
