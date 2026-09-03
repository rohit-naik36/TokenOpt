"""Tests for TokenOpt package imports and drop-in API surface."""

from tokenopt import (
    Anthropic,
    BaseOptimizedClient,
    LocalClient,
    OpenAI,
    TokenOptConfig,
    get_default_config,
)


def test_version():
    import tokenopt

    assert tokenopt.__version__ == "0.1.0"


def test_config_imports():
    config = TokenOptConfig()
    assert config.compression_ratio == 0.5
    assert get_default_config().enable_routing is True


def test_client_classes_exposed():
    assert issubclass(OpenAI, BaseOptimizedClient)
    assert issubclass(Anthropic, BaseOptimizedClient)
    assert issubclass(LocalClient, BaseOptimizedClient)


def test_openai_drop_in_import_style():
    # Mirrors "from openai import OpenAI" -> "from tokenopt import OpenAI"
    client = OpenAI(api_key="test")
    assert isinstance(client, OpenAI)
