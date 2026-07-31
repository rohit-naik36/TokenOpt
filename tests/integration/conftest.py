"""Shared fixtures for integration tests.

All provider HTTP traffic is intercepted in-process by ``httpx.MockTransport``,
injected into the underlying SDK clients via the ``http_client=`` keyword.
No network traffic ever occurs.
"""

from __future__ import annotations

import json

import httpx
import pytest

from tokenopt import Anthropic, OpenAI, TokenOptConfig

OPENAI_RESPONSE = {
    "id": "chatcmpl-mock-001",
    "object": "chat.completion",
    "created": 1700000000,
    "model": "mock-model",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "mock reply"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}

ANTHROPIC_RESPONSE = {
    "id": "msg_mock_001",
    "type": "message",
    "role": "assistant",
    "model": "mock-model",
    "content": [{"type": "text", "text": "mock reply"}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 10, "output_tokens": 5},
}


def make_openai_transport(requests: list) -> httpx.MockTransport:
    """Transport that records OpenAI request bodies and returns a canned reply."""
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=OPENAI_RESPONSE)

    return httpx.MockTransport(handler)


def make_anthropic_transport(requests: list) -> httpx.MockTransport:
    """Transport that records Anthropic request bodies and returns a canned reply."""
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=ANTHROPIC_RESPONSE)

    return httpx.MockTransport(handler)


def make_error_transport() -> httpx.MockTransport:
    """Transport that always answers with HTTP 500."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "mock failure"}})

    return httpx.MockTransport(handler)


@pytest.fixture
def openai_requests() -> list:
    """Bodies of every OpenAI request made during a test."""
    return []


@pytest.fixture
def openai_transport(openai_requests: list) -> httpx.MockTransport:
    return make_openai_transport(openai_requests)


@pytest.fixture
def anthropic_requests() -> list:
    """Bodies of every Anthropic request made during a test."""
    return []


@pytest.fixture
def anthropic_transport(anthropic_requests: list) -> httpx.MockTransport:
    return make_anthropic_transport(anthropic_requests)


@pytest.fixture
def error_transport() -> httpx.MockTransport:
    return make_error_transport()


@pytest.fixture
def openai_client(openai_transport: httpx.MockTransport) -> OpenAI:
    """OpenAI client with default config, wired to the mock transport."""
    return OpenAI(
        api_key="test-key",
        http_client=httpx.Client(transport=openai_transport),
    )


@pytest.fixture
def anthropic_client(anthropic_transport: httpx.MockTransport) -> Anthropic:
    """Anthropic client with empty routing rules, wired to the mock transport."""
    return Anthropic(
        config=TokenOptConfig(),
        api_key="test-key",
        http_client=httpx.Client(transport=anthropic_transport),
    )
