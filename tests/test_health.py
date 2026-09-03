"""Unit tests for the FastAPI app /health endpoint and CORS configuration."""

from fastapi.testclient import TestClient

import tokenopt_proxy_v2 as proxy


def test_health_endpoint():
    client = TestClient(proxy.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["version"] == "2.0.0"


def test_cors_preflight_allowed_origin():
    client = TestClient(proxy.app)
    resp = client.options(
        "/v1/chat/completions",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_cors_rejects_unknown_origin():
    client = TestClient(proxy.app)
    resp = client.options(
        "/v1/chat/completions",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    # A disallowed origin must not be echoed back in allow-origin
    assert resp.headers.get("access-control-allow-origin") != "https://evil.example.com"
