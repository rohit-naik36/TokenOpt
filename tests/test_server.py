"""Tests for TokenOpt FastAPI Optimization Gateway (Prototype v0.1)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from tokenopt import TokenOptConfig, get_prototype_config
from tokenopt.clients import LocalClient
from tokenopt.pipeline.base import OptimizationContext
from tokenopt.pipeline.validator import ValidationDecision, ValidatorStage
from tokenopt.server import create_app


@pytest.fixture
def mock_local_response() -> MagicMock:
    """Create a mock provider response shaped like an OpenAI / Ollama completion."""
    resp = MagicMock()
    resp.id = "chatcmpl-mock-123456"
    resp.created = 1711900000
    resp.choices = [
        MagicMock(
            message=MagicMock(content="Here is the information you requested."),
            finish_reason="stop",
        )
    ]
    resp.usage = MagicMock(
        prompt_tokens=42,
        completion_tokens=18,
        total_tokens=60,
    )
    return resp


@pytest.fixture
def client(mock_local_response: MagicMock) -> TestClient:
    """FastAPI TestClient with stubbed provider call."""
    app = create_app()
    return TestClient(app)


class TestGatewayEndpoints:
    """Test standard gateway endpoints."""

    def test_health_endpoint(self, client: TestClient) -> None:
        """GET /health returns 200 with healthy service metadata."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "tokenopt"
        assert "version" in data

    def test_models_endpoint(self, client: TestClient) -> None:
        """GET /v1/models returns supported model list in OpenAI format."""
        resp = client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        assert isinstance(data["data"], list)
        model_ids = [m["id"] for m in data["data"]]
        assert "llama3.1" in model_ids
        assert "gpt-4o" in model_ids

    def test_valid_chat_completion(
        self, client: TestClient, mock_local_response: MagicMock
    ) -> None:
        """POST /v1/chat/completions returns valid OpenAI response and headers."""
        payload = {
            "model": "llama3.1",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {
                    "role": "user",
                    "content": (
                        "Please kindly describe project Apollo in detail. "
                        "Basically in my opinion it is great."
                    ),
                },
            ],
            "temperature": 0.5,
            "max_tokens": 200,
        }

        with patch.object(LocalClient, "_create_client", return_value=MagicMock()), \
             patch.object(LocalClient, "_call_api", return_value=mock_local_response):
            resp = client.post("/v1/chat/completions", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "chat.completion"
        assert data["model"] == "llama3.1"
        assert len(data["choices"]) == 1
        assert data["choices"][0]["message"]["role"] == "assistant"
        assert data["choices"][0]["message"]["content"] == "Here is the information you requested."
        assert data["choices"][0]["finish_reason"] == "stop"
        assert data["usage"]["completion_tokens"] == 18

        # Telemetry headers
        assert "x-tokenopt-original-tokens" in resp.headers
        assert "x-tokenopt-optimized-tokens" in resp.headers
        assert "x-tokenopt-tokens-saved" in resp.headers
        assert "x-tokenopt-reduction-pct" in resp.headers
        assert "x-tokenopt-pipeline-latency-ms" in resp.headers
        assert "x-tokenopt-model-latency-ms" in resp.headers
        assert "x-tokenopt-cache-hit" in resp.headers
        assert resp.headers["x-tokenopt-cache-hit"] == "false"
        assert resp.headers["x-tokenopt-validation-decision"] == "accept"
        assert resp.headers["x-tokenopt-rollback-applied"] == "false"
        assert int(resp.headers["x-tokenopt-original-tokens"]) > 0

    def test_malformed_request_returns_422(self, client: TestClient) -> None:
        """Invalid schema (missing messages or wrong types) returns 422."""
        resp = client.post("/v1/chat/completions", json={"model": "llama3.1"})
        assert resp.status_code == 422

    def test_empty_messages_returns_400(self, client: TestClient) -> None:
        """Empty messages list returns 400 Bad Request."""
        resp = client.post("/v1/chat/completions", json={"model": "llama3.1", "messages": []})
        assert resp.status_code == 400
        assert "Messages list cannot be empty" in resp.json()["detail"]

    def test_provider_failure_returns_502(self, client: TestClient) -> None:
        """Provider failure / connection error returns 502 Bad Gateway."""
        payload = {
            "model": "llama3.1",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        err = RuntimeError("Ollama connection refused")
        with patch.object(LocalClient, "_create_client", return_value=MagicMock()), \
             patch.object(LocalClient, "_call_api", side_effect=err):
            resp = client.post("/v1/chat/completions", json=payload)

        assert resp.status_code == 502
        assert "LLM provider error" in resp.json()["detail"]
        assert "Ollama connection refused" in resp.json()["detail"]


class TestPrototypeSafetyAndGating:
    """Verify prototype configuration gating and preservation boundary safety."""

    def test_prototype_config_disables_unvalidated_mutators(self) -> None:
        """get_prototype_config() explicitly disables summarization, RAG, and fewshot."""
        cfg = get_prototype_config()
        assert cfg.enable_compression is True
        assert cfg.cache_enabled is False
        assert cfg.enable_routing is False
        assert cfg.enable_summarization is False
        assert cfg.enable_rag is False
        assert cfg.enable_fewshot is False

    def test_default_config_leaves_stages_enabled(self) -> None:
        """Library-wide default config remains unchanged for backward compatibility."""
        cfg = TokenOptConfig()
        assert cfg.enable_compression is True
        assert cfg.cache_enabled is True
        assert cfg.enable_routing is True
        assert cfg.enable_summarization is True
        assert cfg.enable_rag is True
        assert cfg.enable_fewshot is True

    def test_messages_sent_to_provider_match_validated_messages_exactly(
        self, mock_local_response: MagicMock
    ) -> None:
        """Prove that the message list received by _call_api matches what Validator approved."""
        captured_messages: list[list[dict[str, Any]]] = []

        def spy_call_api(messages: list[dict[str, Any]], model: str, **kwargs: Any) -> Any:
            captured_messages.append(messages)
            return mock_local_response

        app = create_app()
        test_client = TestClient(app)

        payload = {
            "model": "llama3.1",
            "messages": [
                {"role": "system", "content": "You are a cluster guardian."},
                {
                    "role": "user",
                    "content": (
                        "Could you please kindly inspect node-99 at https://api.corp/v1? "
                        "Basically in my opinion it had error ERR-0x89AB on 2026-03-31."
                    ),
                },
            ],
        }

        with patch.object(LocalClient, "_create_client", return_value=MagicMock()), \
             patch.object(LocalClient, "_call_api", side_effect=spy_call_api):
            resp = test_client.post("/v1/chat/completions", json=payload)

        assert resp.status_code == 200
        assert len(captured_messages) == 1
        sent_messages = captured_messages[0]

        # Invariants preserved in the sent messages
        content = sent_messages[1]["content"]
        assert "node-99" in content
        assert "https://api.corp/v1" in content
        assert "ERR-0x89AB" in content
        assert "2026-03-31" in content
        # Filler stripped
        assert "kindly" not in content.lower()
        assert "basically" not in content.lower()

    def test_downstream_mutators_do_not_run_under_prototype_config(
        self, mock_local_response: MagicMock
    ) -> None:
        """RAG and summarizer mutations are skipped under prototype gating."""
        # Payload with 'Context:' marker that would trigger RAG mutation if enabled
        rag_prose = (
            "Context:\n[chunk1] Apollo auth docs\n[chunk2] Apollo billing docs\n"
            "Query: How to connect?"
        )
        payload = {
            "model": "llama3.1",
            "messages": [{"role": "user", "content": rag_prose}],
        }

        with patch.object(LocalClient, "_create_client", return_value=MagicMock()), \
             patch.object(LocalClient, "_call_api", return_value=mock_local_response) as mock_api:
            app = create_app()
            test_client = TestClient(app)
            resp = test_client.post("/v1/chat/completions", json=payload)

        assert resp.status_code == 200
        # The messages received by _call_api still have the exact original user content
        called_msgs = mock_api.call_args[0][0]
        assert called_msgs[0]["content"] == rag_prose

    def test_rollback_telemetry_on_invariant_corruption(
        self, mock_local_response: MagicMock
    ) -> None:
        """Simulate an invariant violation and verify rollback headers."""
        raw = "Required token TOKEN-SEC-999 must survive."
        payload = {
            "model": "llama3.1",
            "messages": [{"role": "user", "content": raw}],
        }

        # Mock ValidatorStage to simulate rejection and rollback
        def force_rollback(ctx: OptimizationContext) -> OptimizationContext:
            ctx.messages = [m for m in ctx.original_messages]
            ctx.metrics["validation_decision"] = ValidationDecision.REJECT.value
            ctx.metrics["validation_passed"] = False
            ctx.metrics["rollback_applied"] = True
            ctx.metrics["tokens_saved"] = 0
            return ctx

        with patch.object(LocalClient, "_create_client", return_value=MagicMock()), \
             patch.object(ValidatorStage, "process", side_effect=force_rollback), \
             patch.object(LocalClient, "_call_api", return_value=mock_local_response):
            app = create_app()
            test_client = TestClient(app)
            resp = test_client.post("/v1/chat/completions", json=payload)

        assert resp.status_code == 200
        assert resp.headers["x-tokenopt-validation-decision"] == "reject"
        assert resp.headers["x-tokenopt-rollback-applied"] == "true"
        assert resp.headers["x-tokenopt-tokens-saved"] == "0"

    def test_missing_validation_decision_defaults_to_unknown(
        self, mock_local_response: MagicMock
    ) -> None:
        """When validation decision is empty, header reports 'unknown' instead of 'accept'."""
        payload = {
            "model": "llama3.1",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        def empty_validation(ctx: OptimizationContext) -> OptimizationContext:
            ctx.metrics.pop("validation_decision", None)
            return ctx

        with patch.object(LocalClient, "_create_client", return_value=MagicMock()), \
             patch.object(ValidatorStage, "process", side_effect=empty_validation), \
             patch.object(LocalClient, "_call_api", return_value=mock_local_response):
            app = create_app()
            test_client = TestClient(app)
            resp = test_client.post("/v1/chat/completions", json=payload)

        assert resp.status_code == 200
        assert resp.headers["x-tokenopt-validation-decision"] == "unknown"
