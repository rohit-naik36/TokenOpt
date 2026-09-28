"""Regression test for D-5: the proxy must forward request.model to the optimizer.

Before the fix, ``/v1/chat/completions`` called ``optimizer.optimize(messages,
optimization_level=...)`` without ``model=``, so the adapter fell back to its
``gpt-4o`` default and every token estimate used the wrong tokenizer regardless
of the model the caller requested. This test spies on the adapter's ``optimize``
and asserts the requested model actually reaches it.
"""

from __future__ import annotations

import time
from typing import Any

import jwt as pyjwt
import pytest
import tokenopt_proxy_v2 as proxy
from fastapi.testclient import TestClient

_TEST_SECRET = "test-jwt-secret-0123456789abcdef0123456789"  # 42 bytes


@pytest.fixture(scope="module")
def client():
    with TestClient(proxy.app, raise_server_exceptions=False) as c:
        yield c


def _make_token() -> str:
    payload = {
        "tenant_id": "tenant-a",
        "sub": "user-1",
        "roles": ["admin"],
        "plan": "enterprise",
        "exp": int(time.time()) + 3600,
    }
    return pyjwt.encode(payload, _TEST_SECRET, algorithm="HS256")


def test_request_model_reaches_optimizer(client, monkeypatch):
    proxy.services.config.JWT_SECRET = _TEST_SECRET
    requested_model = "claude-3-5-sonnet-20241022"  # deliberately not the gpt-4o default

    captured: dict[str, Any] = {}
    original = proxy.PromptOptimizer.optimize

    async def _spy(self, messages, model="gpt-4o", **kwargs):
        captured["model"] = model
        return await original(self, messages, model=model, **kwargs)

    monkeypatch.setattr(proxy.PromptOptimizer, "optimize", _spy)

    # Response status is irrelevant (no live providers downstream); we only assert
    # what model the optimizer was invoked with.
    client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {_make_token()}"},
        json={"model": requested_model, "messages": [{"role": "user", "content": "hi there"}]},
    )

    assert captured.get("model") == requested_model, (
        f"optimizer was called with {captured.get('model')!r}, "
        f"expected the request model {requested_model!r}"
    )
    assert captured["model"] != "gpt-4o", "adapter default leaked instead of request.model"
