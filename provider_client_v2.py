"""
TokenOpt v2.0 - Production LLM Provider Integration
Circuit breakers, exponential backoff, fallback routing, streaming support.
"""

import asyncio
import httpx
import time
from typing import Optional, Dict, Any, AsyncGenerator, Callable, List
from dataclasses import dataclass, field
from enum import Enum
import json
from datetime import datetime, timedelta
import logging

logger = logging.getLogger("tokenopt.provider")


class ProviderStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CIRCUIT_OPEN = "circuit_open"


@dataclass
class ProviderConfig:
    """Configuration for a single LLM provider."""
    name: str
    base_url: str
    api_key: str
    timeout: float = 60.0
    max_retries: int = 3
    retry_delay: float = 1.0
    retry_backoff: float = 2.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: float = 60.0
    rate_limit_rpm: int = 10000
    priority: int = 1  # Lower = higher priority for fallback
    models: List[str] = field(default_factory=list)


class CircuitBreaker:
    """
    Circuit breaker pattern for provider resilience.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, reject requests immediately
    - HALF_OPEN: Testing if provider recovered
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = "CLOSED"
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        return self._state

    async def can_execute(self) -> bool:
        async with self._lock:
            if self._state == "CLOSED":
                return True

            if self._state == "OPEN":
                if time.time() - (self._last_failure_time or 0) >= self.recovery_timeout:
                    self._state = "HALF_OPEN"
                    self._half_open_calls = 0
                    logger.info("Circuit breaker entering HALF_OPEN state")
                    return True
                return False

            if self._state == "HALF_OPEN":
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False

            return True

    async def record_success(self):
        async with self._lock:
            if self._state == "HALF_OPEN":
                self._success_count += 1
                if self._success_count >= self.half_open_max_calls:
                    self._state = "CLOSED"
                    self._failure_count = 0
                    self._success_count = 0
                    logger.info("Circuit breaker CLOSED (recovered)")
            else:
                self._failure_count = max(0, self._failure_count - 1)

    async def record_failure(self):
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == "HALF_OPEN":
                self._state = "OPEN"
                logger.warning("Circuit breaker OPEN (half-open test failed)")
            elif self._failure_count >= self.failure_threshold:
                self._state = "OPEN"
                logger.warning(f"Circuit breaker OPEN ({self._failure_count} failures)")


class RateLimiter:
    """Token bucket rate limiter per provider."""

    def __init__(self, requests_per_minute: int):
        self.rpm = requests_per_minute
        self._tokens = requests_per_minute
        self._last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with self._lock:
            now = time.time()
            elapsed = now - self._last_update
            self._tokens = min(self.rpm, self._tokens + elapsed * (self.rpm / 60))
            self._last_update = now

            if self._tokens >= 1:
                self._tokens -= 1
                return True
            return False

    async def wait_time(self) -> float:
        async with self._lock:
            if self._tokens >= 1:
                return 0.0
            return (1 - self._tokens) * (60 / self.rpm)


class LLMProviderClient:
    """
    Production-grade LLM client with:
    - Circuit breaker pattern
    - Exponential backoff retry
    - Rate limiting
    - Streaming support
    - Health monitoring
    """

    def __init__(self, config: ProviderConfig):
        self.config = config
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=config.circuit_breaker_threshold,
            recovery_timeout=config.circuit_breaker_timeout
        )
        self.rate_limiter = RateLimiter(config.rate_limit_rpm)

        self._client: Optional[httpx.AsyncClient] = None
        self._health_status = ProviderStatus.HEALTHY
        self._last_health_check: Optional[datetime] = None
        self._request_count = 0
        self._error_count = 0
        self._total_latency = 0.0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout, connect=10.0),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
                http2=True
            )
        return self._client

    async def health_check(self) -> ProviderStatus:
        """Check provider health with a lightweight request."""
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.config.base_url}/models",
                headers={"Authorization": f"Bearer {self.config.api_key}"},
                timeout=10.0
            )
            if response.status_code == 200:
                self._health_status = ProviderStatus.HEALTHY
            else:
                self._health_status = ProviderStatus.DEGRADED
        except Exception as e:
            self._health_status = ProviderStatus.UNHEALTHY
            logger.warning(f"Health check failed for {self.config.name}: {e}")

        self._last_health_check = datetime.utcnow()
        return self._health_status

    async def chat_completion(
        self,
        request_data: Dict[str, Any],
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Send chat completion request with full resilience stack.
        """
        # Check circuit breaker
        if not await self.circuit_breaker.can_execute():
            raise CircuitBreakerOpenError(f"Circuit breaker open for {self.config.name}")

        # Check rate limiter
        if not await self.rate_limiter.acquire():
            wait = await self.rate_limiter.wait_time()
            logger.warning(f"Rate limit hit for {self.config.name}, waiting {wait:.2f}s")
            await asyncio.sleep(wait)

        client = await self._get_client()
        url = f"{self.config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json"
        }

        last_exception = None

        for attempt in range(self.config.max_retries):
            start_time = time.time()
            try:
                if stream:
                    # Return streaming response iterator
                    return await self._stream_request(client, url, headers, request_data)

                response = await client.post(url, json=request_data, headers=headers)
                response.raise_for_status()

                latency = time.time() - start_time
                self._request_count += 1
                self._total_latency += latency

                await self.circuit_breaker.record_success()
                return response.json()

            except httpx.HTTPStatusError as e:
                latency = time.time() - start_time
                self._error_count += 1
                last_exception = e

                # Don't retry on 4xx errors (client errors)
                if e.response.status_code < 500:
                    await self.circuit_breaker.record_failure()
                    raise ProviderError(
                        f"{self.config.name} client error {e.response.status_code}: {e.response.text}"
                    ) from e

                # Retry on 5xx with backoff
                if attempt < self.config.max_retries - 1:
                    delay = self.config.retry_delay * (self.config.retry_backoff ** attempt)
                    logger.warning(f"{self.config.name} attempt {attempt + 1} failed, retrying in {delay:.1f}s")
                    await asyncio.sleep(delay)
                else:
                    await self.circuit_breaker.record_failure()

            except httpx.TimeoutException as e:
                latency = time.time() - start_time
                self._error_count += 1
                last_exception = e

                if attempt < self.config.max_retries - 1:
                    delay = self.config.retry_delay * (self.config.retry_backoff ** attempt)
                    logger.warning(f"{self.config.name} timeout, retrying in {delay:.1f}s")
                    await asyncio.sleep(delay)
                else:
                    await self.circuit_breaker.record_failure()

            except Exception as e:
                latency = time.time() - start_time
                self._error_count += 1
                last_exception = e
                await self.circuit_breaker.record_failure()
                raise ProviderError(f"{self.config.name} unexpected error: {e}") from e

        # All retries exhausted
        raise ProviderError(
            f"{self.config.name} failed after {self.config.max_retries} attempts: {last_exception}"
        )

    async def _stream_request(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: Dict[str, str],
        request_data: Dict[str, Any]
    ) -> AsyncGenerator[str, None]:
        """Handle streaming requests."""
        request_data["stream"] = True

        async with client.stream("POST", url, json=request_data, headers=headers) as response:
            response.raise_for_status()

            async for chunk in response.aiter_text():
                yield chunk

        await self.circuit_breaker.record_success()

    async def embeddings(
        self,
        texts: List[str],
        model: str = "text-embedding-3-small"
    ) -> List[List[float]]:
        """Get embeddings from provider."""
        if not await self.circuit_breaker.can_execute():
            raise CircuitBreakerOpenError(f"Circuit breaker open for {self.config.name}")

        client = await self._get_client()
        url = f"{self.config.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json"
        }

        # Batch requests if needed (OpenAI allows up to 2048 items)
        all_embeddings = []
        batch_size = 100

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]

            for attempt in range(self.config.max_retries):
                try:
                    response = await client.post(
                        url,
                        json={"input": batch, "model": model},
                        headers=headers
                    )
                    response.raise_for_status()
                    data = response.json()
                    all_embeddings.extend([d["embedding"] for d in data["data"]])
                    await self.circuit_breaker.record_success()
                    break

                except Exception as e:
                    if attempt == self.config.max_retries - 1:
                        await self.circuit_breaker.record_failure()
                        raise ProviderError(f"Embedding failed: {e}") from e
                    await asyncio.sleep(self.config.retry_delay * (self.config.retry_backoff ** attempt))

        return all_embeddings

    def get_stats(self) -> Dict[str, Any]:
        avg_latency = self._total_latency / self._request_count if self._request_count > 0 else 0
        return {
            "provider": self.config.name,
            "status": self._health_status.value,
            "circuit_state": self.circuit_breaker.state,
            "requests": self._request_count,
            "errors": self._error_count,
            "error_rate": round(self._error_count / max(self._request_count, 1) * 100, 2),
            "avg_latency_ms": round(avg_latency * 1000, 2),
            "last_health_check": self._last_health_check.isoformat() if self._last_health_check else None
        }

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


class ProviderError(Exception):
    """Base exception for provider errors."""
    pass


class CircuitBreakerOpenError(ProviderError):
    """Circuit breaker is open."""
    pass


class ProviderRouter:
    """
    Intelligent routing across multiple providers with fallback.

    Features:
    - Cost-aware model selection
    - Health-based routing
    - Automatic failover
    - Load balancing across healthy providers
    """

    def __init__(self):
        self.providers: Dict[str, LLMProviderClient] = {}
        self._health_check_task: Optional[asyncio.Task] = None

    def add_provider(self, config: ProviderConfig):
        """Add a provider to the router."""
        self.providers[config.name] = LLMProviderClient(config)
        logger.info(f"Added provider: {config.name} ({config.base_url})")

    async def start_health_checks(self, interval: float = 30.0):
        """Start periodic health checks."""
        async def _check_loop():
            while True:
                for name, provider in self.providers.items():
                    try:
                        status = await provider.health_check()
                        logger.debug(f"{name} health: {status.value}")
                    except Exception as e:
                        logger.error(f"Health check error for {name}: {e}")
                await asyncio.sleep(interval)

        self._health_check_task = asyncio.create_task(_check_loop())

    async def route_request(
        self,
        model: str,
        request_data: Dict[str, Any],
        stream: bool = False,
        preferred_provider: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Route request to the best available provider.

        Strategy:
        1. If preferred provider specified and healthy, use it
        2. Otherwise, find providers that support the model
        3. Sort by health status and priority
        4. Try each until one succeeds
        """
        candidates = []

        for name, provider in self.providers.items():
            if preferred_provider and name != preferred_provider:
                continue

            # Check if provider supports this model
            if provider.config.models and model not in provider.config.models:
                continue

            # Check circuit breaker
            if not await provider.circuit_breaker.can_execute():
                continue

            # Check health
            if provider._health_status == ProviderStatus.UNHEALTHY:
                continue

            candidates.append(provider)

        # Sort by priority (lower = better) and health
        candidates.sort(key=lambda p: (
            0 if p._health_status == ProviderStatus.HEALTHY else 1,
            p.config.priority
        ))

        if not candidates:
            raise ProviderError(f"No healthy providers available for model {model}")

        last_error = None
        for provider in candidates:
            try:
                logger.info(f"Routing to {provider.config.name} for {model}")
                result = await provider.chat_completion(request_data, stream=stream)

                # Add provider metadata
                if isinstance(result, dict):
                    result["_provider"] = provider.config.name
                    result["_routed_at"] = datetime.utcnow().isoformat()

                return result
            except Exception as e:
                logger.warning(f"Provider {provider.config.name} failed: {e}")
                last_error = e
                continue

        raise ProviderError(f"All providers failed for {model}: {last_error}")

    async def get_cheapest_provider(self, model: str) -> Optional[str]:
        """
        Get the cheapest provider for a given model.
        In production, this would query a pricing API or database.
        """
        # Simplified: prefer providers with lower priority number
        healthy = [
            name for name, p in self.providers.items()
            if p._health_status == ProviderStatus.HEALTHY
            and await p.circuit_breaker.can_execute()
        ]
        if not healthy:
            return None

        # Sort by priority
        sorted_providers = sorted(
            healthy,
            key=lambda n: self.providers[n].config.priority
        )
        return sorted_providers[0]

    async def close_all(self):
        """Close all provider connections."""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        for provider in self.providers.values():
            await provider.close()

    def get_all_stats(self) -> List[Dict[str, Any]]:
        return [p.get_stats() for p in self.providers.values()]
