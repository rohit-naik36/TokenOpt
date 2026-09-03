"""Graceful degradation and provider router fallback tests."""

import pytest

from provider_client_v2 import (
    LLMProviderClient,
    ProviderConfig,
    ProviderError,
    ProviderRouter,
)
from tokenopt_proxy_v2 import DegradedFidelityValidator, ServiceManager


# ---------------------------------------------------------------
# ServiceManager graceful degradation (no external services)
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_service_manager_initializes_without_external_services(monkeypatch, tmp_path):
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    # Redirect the default postgres/redis/kafka DSNs at a dead endpoint so
    # initialize() exercises the fallback paths quickly.
    monkeypatch.setenv("POSTGRES_DSN", "postgresql://u:p@127.0.0.1:1/none")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setenv("KAFKA_BROKERS", "127.0.0.1:1")

    mgr = ServiceManager()
    await mgr.initialize()

    # Every service must be instantiated even though backends are down.
    assert mgr.audit_db is not None
    assert mgr.cache is not None
    assert mgr.event_stream is not None
    assert mgr.provider_router is not None
    # No providers configured, so the router has none.
    assert len(mgr.provider_router.providers) == 0
    # Fails open to the degraded validator.
    assert isinstance(mgr.fidelity_validator, DegradedFidelityValidator)
    assert mgr._initialized is True

    await mgr.shutdown()


@pytest.mark.asyncio
async def test_initialize_is_idempotent(monkeypatch):
    mgr = ServiceManager()
    await mgr.initialize()
    await mgr.initialize()  # second call should short-circuit
    assert mgr._initialized is True
    await mgr.shutdown()


# ---------------------------------------------------------------
# Provider router fallback
# ---------------------------------------------------------------

def _router(*providers):
    router = ProviderRouter()
    for p in providers:
        router.add_provider(p)
    return router


@pytest.mark.asyncio
async def test_router_raises_when_no_healthy_providers():
    router = _router(ProviderConfig(name="p1", base_url="http://x", api_key="k", models=["gpt-4"]))
    router.providers["p1"]._health_status = __import__(
        "provider_client_v2", fromlist=["ProviderStatus"]
    ).ProviderStatus.UNHEALTHY

    with pytest.raises(ProviderError):
        await router.route_request("gpt-4", {"messages": []})


@pytest.mark.asyncio
async def test_router_falls_back_after_provider_failure():
    from provider_client_v2 import ProviderStatus

    router = _router(
        ProviderConfig(name="primary", base_url="http://primary", api_key="k", models=["gpt-4"], priority=1),
        ProviderConfig(name="backup", base_url="http://backup", api_key="k", models=["gpt-4"], priority=2),
    )

    async def _fail(request_data, stream=False):
        raise ProviderError("primary down")

    async def _ok(request_data, stream=False):
        return {"choices": [{"message": {"content": "ok"}}]}

    primary = router.providers["primary"]
    backup = router.providers["backup"]
    primary.chat_completion = _fail
    backup.chat_completion = _ok
    # Make the backup look healthy
    backup._health_status = ProviderStatus.HEALTHY

    result = await router.route_request("gpt-4", {"messages": []})
    assert result["_provider"] == "backup"


@pytest.mark.asyncio
async def test_router_all_providers_fail_raises():
    router = _router(
        ProviderConfig(name="a", base_url="http://a", api_key="k", models=["gpt-4"]),
        ProviderConfig(name="b", base_url="http://b", api_key="k", models=["gpt-4"]),
    )

    async def _fail(request_data, stream=False):
        raise ProviderError("down")

    for name in ("a", "b"):
        router.providers[name].chat_completion = _fail

    with pytest.raises(ProviderError):
        await router.route_request("gpt-4", {"messages": []})


@pytest.mark.asyncio
async def test_router_filters_providers_without_model():
    router = _router(
        ProviderConfig(name="a", base_url="http://a", api_key="k", models=["gpt-3.5"]),
    )
    # Model not supported -> no candidates
    with pytest.raises(ProviderError):
        await router.route_request("gpt-4", {"messages": []})


# ---------------------------------------------------------------
# Circuit breaker integration: when the circuit is OPEN the client must
# reject requests without calling the provider.
# ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_provider_rejects_requests_when_circuit_open():
    from provider_client_v2 import CircuitBreakerOpenError

    config = ProviderConfig(name="p", base_url="http://localhost:1", api_key="k")
    client = LLMProviderClient(config)

    # Open the circuit directly (simulating repeated upstream failures).
    for _ in range(client.circuit_breaker.failure_threshold):
        await client.circuit_breaker.record_failure()
    assert client.circuit_breaker.state == "OPEN"

    # chat_completion checks the breaker first and must raise without I/O.
    with pytest.raises(CircuitBreakerOpenError):
        await client.chat_completion({"messages": []})


@pytest.mark.asyncio
async def test_llm_provider_recovers_after_circuit_timeout():
    config = ProviderConfig(
        name="p", base_url="http://localhost:1", api_key="k",
        circuit_breaker_threshold=1, circuit_breaker_timeout=0.01,
    )
    client = LLMProviderClient(config)

    await client.circuit_breaker.record_failure()
    assert client.circuit_breaker.state == "OPEN"

    # After the recovery timeout the breaker re-enters HALF_OPEN, allowing a
    # limited number of calls through.
    import asyncio
    await asyncio.sleep(0.03)
    assert await client.circuit_breaker.can_execute() is True
    assert client.circuit_breaker.state == "HALF_OPEN"
