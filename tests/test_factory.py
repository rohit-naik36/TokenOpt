"""Tests for the client factory."""

import pytest

from tokenopt import Anthropic, LocalClient, OpenAI, create_client, create_client_from_model
from tokenopt.factory import detect_provider


def test_detect_provider_model_names():
    assert detect_provider(model="gpt-4o") == "openai"
    assert detect_provider(model="gpt-4o-mini") == "openai"
    assert detect_provider(model="claude-3-5-sonnet") == "anthropic"
    assert detect_provider(model="llama3.1") == "local"
    assert detect_provider(model="qwen2.5") == "local"


def test_detect_provider_base_url():
    assert detect_provider(base_url="http://localhost:11434") == "local"
    assert detect_provider() == "openai"


def test_create_client_openai():
    client = create_client(provider="openai", api_key="test")
    assert isinstance(client, OpenAI)


def test_create_client_anthropic():
    client = create_client(provider="anthropic", api_key="test")
    assert isinstance(client, Anthropic)


def test_create_client_local():
    client = create_client(provider="local", model="llama3.1", api_key="test")
    assert isinstance(client, LocalClient)
    assert client.default_local_model == "llama3.1"


def test_create_client_auto_detection():
    assert isinstance(create_client(model="gpt-4o", api_key="test"), OpenAI)
    assert isinstance(create_client(model="claude-3-5-haiku", api_key="test"), Anthropic)
    assert isinstance(create_client(model="mistral", api_key="test"), LocalClient)


def test_create_client_from_model():
    assert isinstance(create_client_from_model("claude-3-5-haiku", api_key="test"), Anthropic)


def test_create_client_unknown_provider():
    with pytest.raises(ValueError):
        create_client(provider="unknown")


def test_create_client_sets_default_model_on_config():
    client = create_client(provider="openai", model="gpt-4o-mini", api_key="test")
    assert client.config.default_model == "gpt-4o-mini"
