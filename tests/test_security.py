"""Security and API endpoint tests.

These verify authentication behavior and request validation, and exercise the
full ServiceManager.initialize() graceful-degradation path with no external
services (LLM providers, Postgres, Redis, Kafka are all unavailable).
"""

import time

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

import tokenopt_proxy_v2 as proxy


@pytest.fixture(scope="session")
def client():
    # Run the app with its lifespan so ServiceManager.initialize() executes,
    # exercising the graceful-degradation path when no external services exist.
    with TestClient(proxy.app, raise_server_exceptions=False) as c:
        yield c


def _uses_lifespan(client):
    return client


_TEST_SECRET = "test-jwt-secret-0123456789abcdef0123456789"  # 42 bytes

def _set_secret(secret=_TEST_SECRET):
    proxy.services.config.JWT_SECRET = secret


def _make_token(secret=_TEST_SECRET, **claims):
    payload = {
        "tenant_id": "tenant-a",
        "sub": "user-1",
        "roles": ["admin"],
        "plan": "enterprise",
        "exp": int(time.time()) + 3600,
    }
    payload.update(claims)
    return pyjwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture(autouse=True)
def _ensure_secret():
    _set_secret()
    _uses_lifespan(None)
    yield


# ---------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------

def test_health_is_public(client):
    assert client.get("/health").status_code == 200


def test_health_reports_services(client):
    resp = client.get("/health")
    body = resp.json()
    assert body["status"] == "healthy"
    # Deployed with no external services, the degraded cache/audit paths
    # should still report so long as they are instantiated.
    assert "services" in body


def test_authenticated_endpoint_requires_token(client):
    resp = client.get("/v1/tokenopt/stats")
    assert resp.status_code in (401, 403)


def test_valid_token_accepted(client):
    resp = client.get(
        "/v1/tokenopt/rollbacks",
        headers={"Authorization": f"Bearer {_make_token()}"},
    )
    # Token was accepted; with no DB the audit store degrades and returns
    # an empty/error payload on 200, or a 5xx. Never 401/403.
    assert resp.status_code not in (401, 403)


def test_stats_with_valid_token(client):
    resp = client.get(
        "/v1/tokenopt/stats",
        headers={"Authorization": f"Bearer {_make_token()}"},
    )
    assert resp.status_code not in (401, 403)


def test_validate_with_valid_token(client):
    resp = client.post(
        "/v1/tokenopt/validate",
        params={"prompt": "Please basically explain how it works in order to help us"},
        headers={"Authorization": f"Bearer {_make_token()}"},
    )
    # Token accepted; optimization runs against the degraded pipeline. Not 401/403.
    assert resp.status_code not in (401, 403)


def test_expired_token_rejected(client):
    token = _make_token(exp=int(time.time()) - 10)
    resp = client.get(
        "/v1/tokenopt/rollbacks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


def test_invalid_token_rejected(client):
    resp = client.get(
        "/v1/tokenopt/rollbacks",
        headers={"Authorization": "Bearer not.a.valid.token"},
    )
    assert resp.status_code == 401


def test_wrong_secret_rejected(client):
    token = _make_token(secret="wrong-secret-value-that-is-long-12345")
    resp = client.get(
        "/v1/tokenopt/rollbacks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


def test_malformed_auth_header_rejected(client):
    resp = client.get(
        "/v1/tokenopt/rollbacks",
        headers={"Authorization": "Basic abc123"},
    )
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------
# Request validation (chat completions)
# ---------------------------------------------------------------

def test_chat_requires_valid_body(client):
    resp = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {_make_token()}"},
        json={},
    )
    assert resp.status_code == 422


def test_chat_rejects_empty_messages(client):
    resp = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {_make_token()}"},
        json={"model": "gpt-4", "messages": []},
    )
    assert resp.status_code == 422


def test_chat_rejects_invalid_optimization_level(client):
    resp = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {_make_token()}"},
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "hello"}],
            "optimization_level": "extreme",
        },
    )
    assert resp.status_code == 422


def test_chat_skip_optimization_passthrough(client):
    # skip_optimization avoids the optimization pipeline; with no provider
    # configured the provider call will fail, but the endpoint must not return
    # 401/403 (auth passed) and must fail with a graceful 5xx or succeed.
    resp = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {_make_token()}"},
        json={
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "hello world"}],
            "skip_optimization": True,
        },
    )
    assert resp.status_code not in (401, 403)
