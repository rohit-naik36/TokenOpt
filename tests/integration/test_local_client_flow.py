"""Integration tests: LocalClient adapters end-to-end flow with stubbed HTTP.

The OpenAI-compatible backend (vLLM, llama.cpp, LM Studio) uses the real openai
SDK with ``httpx.MockTransport`` injected via ``http_client=``. The Ollama
backend is exercised through a fake ``ollama`` module whose ``Client`` sends
HTTP-shaped requests through a mock transport; no real model server is used.
"""

from __future__ import annotations

import json
import sys
import types

import httpx
import openai
import pytest

from tokenopt import LocalClient, create_client


def test_openai_compatible_backend_full_flow(
    openai_transport: httpx.MockTransport, openai_requests: list
) -> None:
    client = LocalClient(
        model="llama3.1",
        base_url="http://localhost:8000/v1",
        http_client=httpx.Client(transport=openai_transport),
    )

    response = client.chat.completions.create(
        messages=[{"role": "user", "content": "Hello"}],
    )

    assert response.choices[0].message.content == "mock reply"
    assert len(openai_requests) == 1
    assert openai_requests[0]["model"] == "llama3.1"
    assert openai_requests[0]["messages"] == [{"role": "user", "content": "Hello"}]

    summary = client.get_metrics_summary()
    assert summary["total_requests"] == 1
    assert summary["error_rate"] == 0.0


def test_local_cache_hit_short_circuits(
    openai_transport: httpx.MockTransport, openai_requests: list
) -> None:
    client = LocalClient(
        model="llama3.1",
        base_url="http://localhost:8000/v1",
        http_client=httpx.Client(transport=openai_transport),
    )
    messages = [{"role": "user", "content": "Hello"}]

    client.chat.completions.create(messages=messages)
    client.chat.completions.create(messages=messages)

    assert len(openai_requests) == 1
    assert client.get_metrics_summary()["cache_hit_rate"] == 0.5


def test_local_provider_error_reraises(error_transport: httpx.MockTransport) -> None:
    client = LocalClient(
        model="llama3.1",
        base_url="http://localhost:8000/v1",
        http_client=httpx.Client(transport=error_transport),
    )

    with pytest.raises(openai.APIStatusError):
        client.chat.completions.create(
            messages=[{"role": "user", "content": "Hello"}],
        )

    assert client.get_metrics_summary()["error_rate"] == 1.0


def test_ollama_backend_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "llama3.1",
                "message": {"content": "mock reply"},
                "prompt_eval_count": 12,
                "eval_count": 6,
            },
        )

    transport = httpx.MockTransport(handler)

    class FakeOllamaClient:
        def __init__(self, host: str | None = None):
            self._host = host

        def chat(self, **kwargs) -> dict:
            response = httpx.Client(transport=transport).post(
                f"{self._host}/api/chat", json=kwargs
            )
            return response.json()

    ollama = types.ModuleType("ollama")
    ollama.Client = FakeOllamaClient
    monkeypatch.setitem(sys.modules, "ollama", ollama)

    client = LocalClient(model="llama3.1", base_url="http://localhost:11434")
    response = client.chat_completion([{"role": "user", "content": "Hello"}])

    assert response.choices[0].message.content == "mock reply"
    assert response.usage.prompt_tokens == 12
    assert response.usage.completion_tokens == 6
    assert client.get_metrics_summary()["total_requests"] == 1
    assert client.metrics_collector.get_recent(1)[0].output_tokens == 6

    body = requests[0]
    assert body["model"] == "llama3.1"
    assert body["messages"] == [{"role": "user", "content": "Hello"}]


def test_local_factory_end_to_end(
    openai_transport: httpx.MockTransport, openai_requests: list
) -> None:
    client = create_client(
        provider="local",
        model="llama3.1",
        base_url="http://localhost:8000/v1",
        http_client=httpx.Client(transport=openai_transport),
    )

    assert isinstance(client, LocalClient)
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": "Hello"}],
    )

    assert response.choices[0].message.content == "mock reply"
    assert openai_requests[0]["model"] == "llama3.1"
