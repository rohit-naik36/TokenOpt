"""Integration tests: OpenAI adapter end-to-end flow with stubbed HTTP.

Every test injects ``httpx.MockTransport`` into the underlying openai SDK via
the ``http_client=`` keyword, so no network traffic ever occurs. The transport
records request bodies so tests can assert what was actually sent.
"""

from __future__ import annotations

from typing import Any

import httpx
import openai
import pytest

from tokenopt import OpenAI, TokenOptConfig, create_client
from tokenopt.observability import RequestMetrics
from tokenopt.pipeline import OptimizationContext, PipelineStage


class BoomStage(PipelineStage):
    """Stage that always fails; proves pipeline fail-open behavior end to end."""

    name = "boom"

    def process(self, ctx: OptimizationContext) -> OptimizationContext:
        raise RuntimeError("boom")


def test_drop_in_chat_completion_full_flow(
    openai_client: OpenAI, openai_requests: list
) -> None:
    response = openai_client.chat.completions.create(
        messages=[{"role": "user", "content": "What is the weather in Paris?"}],
    )

    assert response.choices[0].message.content == "mock reply"
    assert len(openai_requests) == 1
    assert openai_requests[0]["model"] == "gpt-4o-mini"
    assert openai_requests[0]["messages"][0]["role"] == "user"

    summary = openai_client.get_metrics_summary()
    assert summary["total_requests"] == 1
    assert summary["error_rate"] == 0.0
    assert summary["optimization_usage"]["routing"] == 1


def test_request_body_optimized_before_provider_call(
    openai_client: OpenAI, openai_requests: list
) -> None:
    original = (
        "please kindly implement a function that computes prime numbers. "
        + "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod " * 20
    )
    openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": original}],
    )

    body = openai_requests[0]
    assert body["model"] == "gpt-4o"
    sent_content = body["messages"][0]["content"]
    assert "please" not in sent_content
    assert len(sent_content) < len(original)


def test_identical_second_call_hits_cache(
    openai_client: OpenAI, openai_requests: list
) -> None:
    messages = [{"role": "user", "content": "What is the weather in Paris?"}]

    first = openai_client.chat.completions.create(model="gpt-4o", messages=messages)
    second = openai_client.chat.completions.create(model="gpt-4o", messages=messages)

    assert first.choices[0].message.content == second.choices[0].message.content
    assert len(openai_requests) == 1
    summary = openai_client.get_metrics_summary()
    assert summary["total_requests"] == 2
    assert summary["cache_hit_rate"] == 0.5


def test_provider_error_reraises_and_records_metrics(
    error_transport: httpx.MockTransport,
) -> None:
    client = OpenAI(
        api_key="test-key",
        http_client=httpx.Client(transport=error_transport),
    )

    with pytest.raises(openai.APIStatusError):
        client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
        )

    summary = client.get_metrics_summary()
    assert summary["total_requests"] == 1
    assert summary["error_rate"] == 1.0
    assert "500" in client.metrics_collector.get_recent(1)[0].error


def test_stage_failure_fails_open_end_to_end(
    openai_client: OpenAI, openai_requests: list
) -> None:
    openai_client.pipeline.stages.append(BoomStage())

    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello"}],
    )

    assert response.choices[0].message.content == "mock reply"
    assert len(openai_requests) == 1
    assert openai_client.get_metrics_summary()["error_rate"] == 0.0


def test_disabled_compression_passes_messages_through(
    openai_transport: httpx.MockTransport, openai_requests: list
) -> None:
    client = OpenAI(
        config=TokenOptConfig(enable_compression=False, enable_routing=False),
        api_key="test-key",
        http_client=httpx.Client(transport=openai_transport),
    )
    original = "please give me a detailed answer about penguins"

    client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": original}],
    )

    body = openai_requests[0]
    assert body["model"] == "gpt-4o"
    assert body["messages"][0]["content"] == original


def test_metrics_callback_receives_request_metrics(
    openai_transport: httpx.MockTransport,
) -> None:
    collected: list[RequestMetrics] = []
    client = OpenAI(
        config=TokenOptConfig(metrics_callback=collected.append),
        api_key="test-key",
        http_client=httpx.Client(transport=openai_transport),
    )

    client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "hi there"}],
    )

    assert len(collected) == 1
    metric = collected[0]
    assert metric.error is None
    assert metric.cache_hit is False
    assert metric.output_tokens == 5
    assert metric.estimated_cost > 0.0


def test_factory_builds_working_openai_client(
    openai_transport: httpx.MockTransport,
) -> None:
    client: Any = create_client(
        provider="openai",
        model="gpt-4o",
        api_key="test-key",
        http_client=httpx.Client(transport=openai_transport),
    )

    assert isinstance(client, OpenAI)
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": "Hello"}],
    )
    assert response.choices[0].message.content == "mock reply"
