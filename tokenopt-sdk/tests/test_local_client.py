"""Tests for the LocalClient (Ollama / vLLM / llama.cpp)."""

from types import SimpleNamespace

import pytest

from tokenopt.clients.local_client import LocalClient


class FakeLocalClient(LocalClient):
    """Stubbed LocalClient that never touches the network."""

    def _create_client(self):
        return object()

    def _call_api(self, messages, model, **kwargs):
        assert model == self.default_local_model
        return SimpleNamespace(
            model=model,
            choices=[SimpleNamespace(message=SimpleNamespace(content="local answer"))],
            usage=SimpleNamespace(prompt_tokens=25, completion_tokens=5, total_tokens=30),
        )


@pytest.fixture
def client():
    return FakeLocalClient(api_key="test")


def test_default_model():
    assert LocalClient.OLLAMA_DEFAULT_URL == "http://localhost:11434"
    assert FakeLocalClient(api_key="test").default_local_model == "llama3.1"
    assert FakeLocalClient(api_key="test", model="qwen2.5").default_local_model == "qwen2.5"


def test_backend_detection_ollama():
    client = FakeLocalClient(api_key="test")
    assert client._detect_backend() == "ollama"


def test_backend_detection_openai_compatible():
    client = FakeLocalClient(api_key="test", base_url="http://localhost:8000/v1")
    assert client._detect_backend() == "openai"


def test_chat_completion_uses_local_model(client):
    response = client.chat_completion([{"role": "user", "content": "Hello"}])
    assert response.choices[0].message.content == "local answer"
    assert response.usage.prompt_tokens == 25


def test_extract_content_and_usage(client):
    response = client.chat_completion([{"role": "user", "content": "Hi"}])
    assert client._extract_response_content(response) == "local answer"
    usage = client._extract_usage(response)
    assert usage["total_tokens"] == 30


def test_metrics_recorded(client):
    client.chat_completion([{"role": "user", "content": "Hello there"}])
    summary = client.get_metrics_summary()
    assert summary["total_requests"] == 1
    assert summary["error_rate"] == 0.0


def test_cache_hit_on_duplicate(client):
    messages = [{"role": "user", "content": "Repeat me please"}]
    client.chat_completion(messages)
    client.chat_completion(messages)
    summary = client.get_metrics_summary()
    assert summary["total_requests"] == 2
    assert summary["cache_hit_rate"] == 0.5


def test_pipeline_skips_cloud_router_by_default():
    client = FakeLocalClient(api_key="test")
    stage_names = [s.name for s in client.pipeline.stages]
    assert "router" not in stage_names
    assert "cache" in stage_names


def test_normalize_ollama_dict_response():
    client = FakeLocalClient(api_key="test")
    raw = {
        "model": "llama3.1",
        "message": {"role": "assistant", "content": "dict answer"},
        "prompt_eval_count": 12,
        "eval_count": 4,
    }
    normalized = client._normalize_ollama_response(raw)
    assert normalized.choices[0].message.content == "dict answer"
    assert normalized.usage.total_tokens == 16


def test_normalize_ollama_object_response():
    client = FakeLocalClient(api_key="test")
    raw = SimpleNamespace(
        model="llama3.1",
        message=SimpleNamespace(role="assistant", content="object answer"),
        prompt_eval_count=10,
        eval_count=3,
    )
    normalized = client._normalize_ollama_response(raw)
    assert normalized.choices[0].message.content == "object answer"
    assert normalized.usage.completion_tokens == 3
