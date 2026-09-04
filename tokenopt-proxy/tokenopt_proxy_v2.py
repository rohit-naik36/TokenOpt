"""
TokenOpt v2.0 - Production API Proxy
Integrates: real embeddings, circuit breaker providers, PostgreSQL audit, Redis cache, Kafka events.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
import asyncio
import json
import secrets
import time
import os
import uuid
import jwt
from datetime import datetime, timedelta, timezone
import logging
from functools import lru_cache

# Optional real tokenizer (falls back to the SDK heuristic when unavailable)
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

# Import v2 components
from fidelity_validator_v2 import EmbeddingFidelityValidator
from provider_client_v2 import ProviderRouter, ProviderConfig, ProviderError
from persistence_layer_v2 import AuditDatabase, DistributedCache, EventStreamer, AuditLogEntry

# Import TokenOpt optimizer SDK (standalone, embeddable optimization engine)
from tokenopt_optimizer import (
    DegradedFidelityValidator as SDK_DegradedFidelityValidator,
    OptimizerConfig,
    PromptOptimizer,
)

# Optional dependencies (checked early so constants are available everywhere)
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

try:
    import headroom
    from headroom import compress as headroom_compress
    from headroom import CompressConfig as HeadroomConfig
    HEADROOM_AVAILABLE = True
except ImportError:
    headroom = None
    headroom_compress = None
    HeadroomConfig = None
    HEADROOM_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tokenopt.v2")

# ============================================================
# Configuration
# ============================================================

class AppConfig:
    """Application configuration loaded from environment."""

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        raw = os.getenv(name)
        if raw is None:
            return default
        try:
            return float(raw)
        except (TypeError, ValueError):
            logger.warning(f"Invalid {name}={raw!r}, using default {default}")
            return default

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        raw = os.getenv(name)
        if raw is None:
            return default
        try:
            return int(raw)
        except (TypeError, ValueError):
            logger.warning(f"Invalid {name}={raw!r}, using default {default}")
            return default

    @staticmethod
    def _env_bool(name: str, default: bool) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return raw.lower() in ("1", "true", "yes", "on")

    # Database
    POSTGRES_DSN = os.getenv("POSTGRES_DSN", "")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_CLUSTER = _env_bool("REDIS_CLUSTER", False)
    KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "localhost:9092")

    # AI Providers
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY", "")
    AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    # Google Gemini — free tier, no credit card needed (aistudio.google.com)
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

    # Security
    JWT_SECRET = os.getenv("JWT_SECRET", "")
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")

    # Optimization
    FIDELITY_THRESHOLD = _env_float("FIDELITY_THRESHOLD", 0.995)
    ENABLE_LLM_JUDGE = _env_bool("ENABLE_LLM_JUDGE", True)
    ENABLE_HEADROOM = _env_bool("ENABLE_HEADROOM", True)
    HEADROOM_MIN_TOKENS = _env_int("HEADROOM_MIN_TOKENS", 100)
    HEADROOM_TARGET_RATIO = _env_float("HEADROOM_TARGET_RATIO", 0.5)

    # Token/quality controls for AAVA
    USE_TIKTOKEN = _env_bool("USE_TIKTOKEN", True)
    # Minimum token savings (percent) below which optimization is skipped so we
    # never report meaningless single-digit savings or add pointless latency.
    MIN_SAVINGS_PCT = _env_float("MIN_SAVINGS_PCT", 2.0)
    # When true (AAVA production), refuse to serve with the fails-open degraded
    # validator because fidelity numbers would be meaningless. Off by default so
    # the existing fails-open dev/demo behavior is preserved.
    REQUIRE_REAL_FIDELITY = _env_bool("REQUIRE_REAL_FIDELITY", False)

    # Performance
    MAX_CONCURRENT_REQUESTS = max(_env_int("MAX_CONCURRENT_REQUESTS", 100), 1)
    REQUEST_TIMEOUT = _env_float("REQUEST_TIMEOUT", 60.0)

    # Pricing (cost per token, used for savings estimates)
    MODEL_PRICING = {
        "gpt-4": 0.00003,
        "gpt-4-turbo": 0.00001,
        "gpt-3.5-turbo": 0.0000015,
        "claude-3-opus": 0.000015,
        "claude-3-sonnet": 0.000003,
        "claude-3-haiku": 0.00000025,
        # Gemini (free tier — cost is effectively $0 for demo)
        "gemini-1.5-flash": 0.0000000,
        "gemini-1.5-pro": 0.0000035,
        "gemini-2.0-flash": 0.0000000,
    }
    DEFAULT_TOKEN_PRICE = 0.00003

    @classmethod
    def get_token_price(cls, model: str) -> float:
        """Return per-token price for *model*, falling back to DEFAULT_TOKEN_PRICE."""
        return cls.MODEL_PRICING.get(model, cls.DEFAULT_TOKEN_PRICE)

    @staticmethod
    @lru_cache(maxsize=64)
    def _encoding_for(model: str):
        """Return the tiktoken encoding for *model*, best-effort."""
        if not TIKTOKEN_AVAILABLE:
            return None
        try:
            return tiktoken.encoding_for_model(model)
        except KeyError:
            try:
                return tiktoken.get_encoding("cl100k_base")
            except Exception:  # noqa: BLE001
                return None

    @classmethod
    def make_token_counter(cls, model: str = "gpt-4"):
        """Build an SDK-compatible ``Callable[[str], int]`` token counter.

        Uses tiktoken (per-model) when available; otherwise falls back to
        ``None`` so the SDK uses its internal word-count heuristic.
        """
        if not cls.USE_TIKTOKEN or not TIKTOKEN_AVAILABLE:
            return None

        def _count(text: str) -> int:
            enc = cls._encoding_for(model)
            if enc is None:
                return int(len(text.split()) / 0.75)
            return len(enc.encode(text))

        return _count

# ============================================================
# Pydantic Models
# ============================================================

class ChatMessage(BaseModel):
    role: str
    content: str
    name: Optional[str] = None

class ChatCompletionRequest(BaseModel):
    model: str = Field(..., min_length=1, description="Model name, e.g. gpt-4")
    messages: List[ChatMessage] = Field(
        ..., min_length=1, description="Chat messages (max 1 system + rest user/assistant)"
    )
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1)
    top_p: Optional[float] = Field(1.0, ge=0.0, le=1.0)
    frequency_penalty: Optional[float] = Field(0.0, ge=-2.0, le=2.0)
    presence_penalty: Optional[float] = Field(0.0, ge=-2.0, le=2.0)
    stream: Optional[bool] = False
    user: Optional[str] = None
    # TokenOpt extensions
    optimization_level: Optional[str] = Field("standard", pattern="^(standard|aggressive|conservative)$")
    skip_optimization: Optional[bool] = False
    fidelity_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    preferred_provider: Optional[str] = None

class EmbeddingRequest(BaseModel):
    input: str | List[str]
    model: str = "text-embedding-3-small"
    encoding_format: Optional[str] = "float"

# ============================================================
# FastAPI Application
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown lifecycle."""
    await services.initialize()
    yield
    await services.shutdown()

app = FastAPI(
    title="TokenOpt Enterprise v2.0",
    description="Production AI token optimization with real embeddings, circuit breakers, and audit trail",
    version="2.0.0",
    lifespan=lifespan
)

_cors_default = ["http://localhost:3000", "http://localhost:5173", "http://localhost:8080"]
_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
if _cors_origins:
    # Explicitly configured origins. No wildcard unless the env var is literally "*".
    _cors_allowed = _cors_origins
    _cors_credentials = not ("*" in _cors_origins)
else:
    # Default to local development origins; never wildcard-open CORS by default.
    _cors_allowed = _cors_default
    _cors_credentials = True
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allowed,
    allow_credentials=_cors_credentials,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
logger.info(f"CORS configured: allow_origins={_cors_allowed}, allow_credentials={_cors_credentials}")

security = HTTPBearer()

# ============================================================
# Global Services (initialized on startup)
# ============================================================

# Fails-open fidelity validator now lives in the TokenOpt optimizer SDK.
# Re-export it here so existing imports / tests against the proxy keep working.
DegradedFidelityValidator = SDK_DegradedFidelityValidator


def minimum_savings_rollback(
    opt_result: Dict[str, Any],
    min_savings_pct: float,
    original_prompt: str,
) -> bool:
    """Decide whether an optimization result saves too little to be worthwhile.

    When savings (percentage of tokens removed) fall below *min_savings_pct*,
    the prompt is reverted to the original and ``opt_result`` is updated to
    reflect the rollback. Returns ``True`` if a rollback was applied.
    """
    if opt_result.get("was_skipped") or opt_result.get("was_rolled_back"):
        return False
    orig_tokens = opt_result.get("original_tokens", 0)
    if orig_tokens <= 0:
        return False
    savings_pct = (1 - opt_result["optimized_tokens"] / orig_tokens) * 100
    if savings_pct >= min_savings_pct:
        return False

    opt_result["optimized_prompt"] = original_prompt
    opt_result["optimized_tokens"] = orig_tokens
    opt_result["was_rolled_back"] = True
    opt_result["rollback_reason"] = (
        f"Savings {savings_pct:.2f}% below minimum {min_savings_pct}%"
    )
    return True


def _one_in(rate: int) -> bool:
    """Return True with probability 1/rate, uniformly (cryptographically random).

    Used for fair, unbiased sampling of expensive operations (e.g. deep response
    validation). ``rate`` must be >= 1.
    """
    if rate <= 1:
        return True
    return secrets.randbelow(rate) == 0


_OPTIMIZER_CACHE: dict[str, Any] = {}


def build_optimizer(model: str = "gpt-4"):
    """Return an SDK ``PromptOptimizer`` wired to the live global services.

    The SDK optimizer is fully dependency-injected; here we connect it to the
    process-wide cache and fidelity validator so the proxy and the standalone
    engine share the same backends. The tokenizer is built for ``model`` so
    token counts match the actual model tokenization when available.

    Optimizers are cached per model (they are stateless between calls) so a
    request does not pay the construction cost every time. The cache is keyed
    by ``(model, validator_id, cache_id)`` so re-initialized backends invalidate
    stale optimizers automatically.
    """
    validator_id = id(services.fidelity_validator)
    cache_id = id(services.cache)
    key = (model, validator_id, cache_id)
    cached = _OPTIMIZER_CACHE.get(key)
    if cached is not None:
        return cached

    cfg = services.config
    config = OptimizerConfig(
        enable_headroom=cfg.ENABLE_HEADROOM,
        headroom_target_ratio=cfg.HEADROOM_TARGET_RATIO,
        headroom_min_tokens=cfg.HEADROOM_MIN_TOKENS,
        tokenizer=cfg.make_token_counter(model),
    )
    optimizer = PromptOptimizer(
        config=config,
        cache=services.cache,
        validator=services.fidelity_validator,
    )
    _OPTIMIZER_CACHE[key] = optimizer
    return optimizer


class ServiceManager:
    """Manages all production services lifecycle."""

    def __init__(self):
        self.config = AppConfig()
        self.fidelity_validator: Optional[EmbeddingFidelityValidator] = None
        self.provider_router: Optional[ProviderRouter] = None
        self.audit_db: Optional[AuditDatabase] = None
        self.cache: Optional[DistributedCache] = None
        self.event_stream: Optional[EventStreamer] = None
        self._semaphore = asyncio.Semaphore(self.config.MAX_CONCURRENT_REQUESTS)
        self._initialized = False

    async def initialize(self):
        """Initialize all services."""
        if self._initialized:
            return

        logger.info("Initializing TokenOpt v2.0 services...")

        # Startup validation
        if not self.config.JWT_SECRET:
            logger.critical(
                "JWT_SECRET is not set! Authentication will reject all requests. "
                "Set the JWT_SECRET environment variable before running in production."
            )
        elif len(self.config.JWT_SECRET.encode("utf-8")) < 32:
            raise RuntimeError(
                "JWT_SECRET must be at least 32 bytes long for secure HMAC "
                "signing. Generate one with e.g. `openssl rand -base64 48`."
            )

        # 1. Fidelity Validator
        try:
            self.fidelity_validator = EmbeddingFidelityValidator(
                embedding_model="sentence-transformers/all-MiniLM-L6-v2",
                use_openai_embeddings=not SENTENCE_TRANSFORMERS_AVAILABLE,
                openai_api_key=self.config.OPENAI_API_KEY,
                fidelity_threshold=self.config.FIDELITY_THRESHOLD,
                enable_llm_judge=self.config.ENABLE_LLM_JUDGE,
                llm_judge_model="gpt-4"
            )
            logger.info("âœ… Fidelity validator initialized")
        except Exception as e:
            # Fails open for dev/demo, but never for a production-like run:
            # reporting fidelity from a pass-through validator would be a lie
            # to paying AAVA clients. When REQUIRE_REAL_FIDELITY is on we refuse
            # to start rather than serve misleading numbers.
            if self.config.REQUIRE_REAL_FIDELITY:
                raise RuntimeError(
                    "REQUIRE_REAL_FIDELITY is enabled but no real embedding "
                    "validator could be initialized. Configure an embedding "
                    "backend (sentence-transformers or OPENAI_API_KEY), or set "
                    "REQUIRE_REAL_FIDELITY=false to explicitly allow the "
                    "fails-open degraded validator (dev/demo only)."
                ) from e
            logger.warning(f"Fidelity validator unavailable ({e}); using degraded passthrough (fails open)")
            self.fidelity_validator = DegradedFidelityValidator()

        # 2. Provider Router
        self.provider_router = ProviderRouter()

        if self.config.OPENAI_API_KEY:
            self.provider_router.add_provider(ProviderConfig(
                name="openai",
                base_url="https://api.openai.com/v1",
                api_key=self.config.OPENAI_API_KEY,
                models=["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo", "text-embedding-ada-002", "text-embedding-3-small"],
                priority=1
            ))

        if self.config.AZURE_OPENAI_KEY and self.config.AZURE_OPENAI_ENDPOINT:
            self.provider_router.add_provider(ProviderConfig(
                name="azure",
                base_url=self.config.AZURE_OPENAI_ENDPOINT,
                api_key=self.config.AZURE_OPENAI_KEY,
                models=["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"],
                priority=2
            ))

        if self.config.ANTHROPIC_API_KEY:
            self.provider_router.add_provider(ProviderConfig(
                name="anthropic",
                base_url="https://api.anthropic.com/v1",
                api_key=self.config.ANTHROPIC_API_KEY,
                models=["claude-3-opus", "claude-3-sonnet", "claude-3-haiku"],
                priority=3
            ))

        if self.config.GEMINI_API_KEY:
            # Gemini exposes an OpenAI-compatible endpoint — no SDK change needed.
            # Free tier: 15 req/min, 1M tokens/day — ideal for demos.
            self.provider_router.add_provider(ProviderConfig(
                name="gemini",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                api_key=self.config.GEMINI_API_KEY,
                models=["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
                priority=4
            ))

        await self.provider_router.start_health_checks(interval=30.0)
        logger.info("âœ… Provider router initialized")

        # 3. Audit Database
        self.audit_db = AuditDatabase(
            dsn=self.config.POSTGRES_DSN,
            retention_days=90
        )
        await self.audit_db.initialize()
        logger.info("âœ… Audit database initialized")

        # 4. Distributed Cache
        self.cache = DistributedCache(
            redis_url=self.config.REDIS_URL,
            cluster_mode=self.config.REDIS_CLUSTER,
            ttl_seconds=3600
        )
        await self.cache.initialize()
        logger.info("âœ… Distributed cache initialized")

        # 5. Event Streamer
        self.event_stream = EventStreamer(
            bootstrap_servers=self.config.KAFKA_BROKERS
        )
        await self.event_stream.initialize()
        logger.info("âœ… Event streamer initialized")

        self._initialized = True
        logger.info("ðŸš€ TokenOpt v2.0 fully initialized")

    async def shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down TokenOpt v2.0...")

        if self.provider_router:
            await self.provider_router.close_all()
        if self.audit_db:
            await self.audit_db.close()
        if self.cache:
            await self.cache.close()
        if self.event_stream:
            await self.event_stream.close()

        logger.info("ðŸ‘‹ TokenOpt v2.0 shutdown complete")

# Global service manager
services = ServiceManager()

# ============================================================
# Authentication
# ============================================================

async def authenticate(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """JWT-based authentication."""
    secret = services.config.JWT_SECRET
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Authentication unavailable: JWT_SECRET is not configured. Set the JWT_SECRET environment variable."
        )
    try:
        token = credentials.credentials
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"verify_exp": True}
        )

        return {
            "tenant_id": payload.get("tenant_id", "default"),
            "user_id": payload.get("sub", "anonymous"),
            "roles": payload.get("roles", ["user"]),
            "plan": payload.get("plan", "standard")
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired") from None
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token") from None
    except Exception as exc:  # noqa: BLE001 — never let auth crash with 500
        logger.error("Unexpected error in authenticate: %s", exc)
        raise HTTPException(status_code=401, detail="Authentication failed") from None

# ============================================================
# Optimization Engine (provided by the TokenOpt optimizer SDK)
# ============================================================

# PromptOptimizer / SemanticCompressorV2 are imported from the SDK at the top
# of this module. See build_optimizer() for constructing a wired engine.


# ============================================================
# API Endpoints
# ============================================================

@app.get("/health")
async def health_check():
    """Comprehensive health check."""
    health = {
        "status": "healthy",
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": {}
    }

    # Check each service
    if services.fidelity_validator:
        health["services"]["fidelity_validator"] = "ok"
    if services.provider_router:
        provider_stats = services.provider_router.get_all_stats()
        health["services"]["providers"] = provider_stats
    if services.audit_db:
        health["services"]["audit_db"] = "connected" if services.audit_db._pool else "fallback"
    if services.cache:
        cache_stats = await services.cache.get_stats()
        health["services"]["cache"] = cache_stats

    return health

@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    background_tasks: BackgroundTasks,
    http_request: Request,
    tenant: Dict = Depends(authenticate)
):
    """
    Production chat completions with full optimization pipeline.
    """
    request_id = str(uuid.uuid4())
    start_time = time.time()

    # Concurrency limit
    async with services._semaphore:
        try:
            # 1. Optimize prompt
            if request.skip_optimization:
                # Bypass the entire optimization pipeline (fails safe passthrough)
                full_prompt = "\n".join([f"{m.role}: {m.content}" for m in request.messages])
                opt_result = {
                    "optimized_prompt": full_prompt,
                    "optimized_tokens": int(len(full_prompt.split()) / 0.75),
                    "techniques": ["skipped"],
                    "cache_hit": False,
                    "original_tokens": int(len(full_prompt.split()) / 0.75),
                    "fidelity_score": 1.0,
                    "fidelity_passed": True,
                    "fidelity_details": {"engine": "skipped"},
                    "was_skipped": True
                }
            else:
                optimizer = build_optimizer(request.model)
                opt_result = await optimizer.optimize(
                    request.messages,
                    optimization_level=request.optimization_level or "standard"
                )

            # 2. Check fidelity threshold
            custom_threshold = request.fidelity_threshold or services.config.FIDELITY_THRESHOLD
            if opt_result["fidelity_score"] < custom_threshold:
                # Use original prompt
                opt_result["optimized_prompt"] = "\n".join([f"{m.role}: {m.content}" for m in request.messages])
                opt_result["optimized_tokens"] = opt_result["original_tokens"]
                opt_result["was_rolled_back"] = True
                opt_result["rollback_reason"] = (
                    f"Fidelity {opt_result['fidelity_score']:.3f} below threshold {custom_threshold}"
                )

            # 2b. Minimum savings floor: don't bother sending a compressed prompt
            # that saves almost nothing — it adds latency and risks client trust
            # with a meaningless savings report. Revert to original if savings
            # are below MIN_SAVINGS_PCT.
            minimum_savings_rollback(
                opt_result,
                services.config.MIN_SAVINGS_PCT,
                "\n".join([f"{m.role}: {m.content}" for m in request.messages]),
            )

            # 3. Build request for provider
            # The optimized prompt is the full conversation in compressed form,
            # so it is sent once as a single user message; system prompts are
            # preserved verbatim.
            optimized_messages = []
            for msg in request.messages:
                if msg.role == "system":
                    optimized_messages.append({"role": "system", "content": msg.content})
            optimized_messages.append({"role": "user", "content": opt_result["optimized_prompt"]})

            request_data = {
                "model": request.model,
                "messages": optimized_messages,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "top_p": request.top_p,
                "frequency_penalty": request.frequency_penalty,
                "presence_penalty": request.presence_penalty,
                "stream": request.stream,
                "user": request.user
            }

            # 4. Route to provider
            provider_start = time.time()

            if request.stream:
                # Streaming response
                stream_error = None

                async def stream_generator():
                    nonlocal stream_error
                    full_response = ""
                    try:
                        result = await services.provider_router.route_request(
                            model=request.model,
                            request_data=request_data,
                            stream=True,
                            preferred_provider=request.preferred_provider
                        )
                        async for chunk in result:
                            yield chunk
                            # Accumulate for audit
                            if isinstance(chunk, str) and chunk.startswith("data: "):
                                data = chunk[6:]
                                if data != "[DONE]":
                                    try:
                                        parsed = json.loads(data)
                                        if parsed.get("choices"):
                                            delta = parsed["choices"][0].get("delta", {})
                                            if "content" in delta:
                                                full_response += delta["content"]
                                    except Exception:
                                        logger.debug("Skipping non-parseable SSE chunk", exc_info=True)
                    except Exception as e:
                        # Never leak internal details to the client (S-4)
                        stream_error = e
                        logger.exception("Streaming error")
                        yield "data: {\"error\": \"upstream stream failed\"}\n\n"
                    finally:
                        try:
                            stream_latency = time.time() - provider_start
                            audit_entry = AuditLogEntry(
                                tenant_id=tenant["tenant_id"],
                                user_id=tenant["user_id"],
                                request_id=request_id,
                                provider=request.model,
                                model=request.model,
                                original_prompt="\n".join([f"{m.role}: {m.content}" for m in request.messages]),
                                optimized_prompt=opt_result["optimized_prompt"],
                                original_tokens=opt_result["original_tokens"],
                                optimized_tokens=opt_result["optimized_tokens"],
                                techniques=opt_result["techniques"],
                                cache_hit=opt_result["cache_hit"],
                                fidelity_score=opt_result.get("fidelity_score", 0.0),
                                fidelity_passed=opt_result.get("fidelity_passed", False),
                                was_optimized=opt_result["optimized_tokens"] < opt_result["original_tokens"],
                                was_rolled_back=opt_result.get("was_rolled_back", False),
                                rollback_reason=opt_result.get("rollback_reason"),
                                optimization_latency_ms=(provider_start - start_time) * 1000,
                                provider_latency_ms=stream_latency * 1000,
                                total_latency_ms=(time.time() - start_time) * 1000,
                                estimated_cost_original=0.0,
                                estimated_cost_optimized=0.0,
                                cost_savings=0.0,
                                response_tokens=len(full_response.split()),
                                finish_reason="stream" if not stream_error else "error",
                                ip_address=http_request.client.host if http_request.client else None,
                                user_agent=http_request.headers.get("user-agent")
                            )
                            background_tasks.add_task(services.audit_db.log_request, audit_entry)
                            background_tasks.add_task(services.event_stream.emit_request, audit_entry)
                        except Exception:
                            logger.exception("Streaming audit failed")

                return StreamingResponse(
                    stream_generator(),
                    media_type="text/event-stream"
                )

            # Non-streaming
            result = await services.provider_router.route_request(
                model=request.model,
                request_data=request_data,
                stream=False,
                preferred_provider=request.preferred_provider
            )

            provider_latency = time.time() - provider_start
            total_latency = time.time() - start_time

            # 5. Post-optimization fidelity check (if we have response)
            if result.get("choices"):
                response_content = result["choices"][0].get("message", {}).get("content", "")

                # Only do expensive response validation for ~5% of requests (sampled).
                # Use a uniform random sample (not hash(request_id) % N, whose
                # distribution is not guaranteed uniform) so every request has an
                # equal chance of being deep-validated.
                if _one_in(20) and services.config.ENABLE_LLM_JUDGE:
                    # Build baseline request
                    baseline_request = request_data.copy()
                    baseline_request["messages"] = [{"role": m.role, "content": m.content} for m in request.messages]

                    try:
                        baseline_result = await services.provider_router.route_request(
                            model=request.model,
                            request_data=baseline_request,
                            stream=False,
                            preferred_provider=result.get("_provider")
                        )
                        baseline_content = baseline_result["choices"][0].get("message", {}).get("content", "")

                        # Validate response fidelity
                        response_fidelity = await services.fidelity_validator.validate(
                            original_prompt="\n".join([f"{m.role}: {m.content}" for m in request.messages]),
                            optimized_prompt=opt_result["optimized_prompt"],
                            baseline_response=baseline_content,
                            optimized_response=response_content
                        )

                        opt_result["response_fidelity"] = response_fidelity.overall
                        opt_result["response_fidelity_passed"] = response_fidelity.passed

                        if not response_fidelity.passed:
                            # Rollback: return baseline result
                            result = baseline_result
                            opt_result["was_rolled_back"] = True
                            opt_result["rollback_reason"] = (
                                f"Response fidelity {response_fidelity.overall:.3f} below threshold"
                            )

                    except Exception as e:
                        logger.warning(f"Response validation failed: {e}")

            # 6. Attach TokenOpt metadata
            usage = result.get("usage", {})
            token_price = services.config.get_token_price(request.model)
            original_cost = opt_result["original_tokens"] * token_price
            optimized_cost = opt_result["optimized_tokens"] * token_price

            result["tokenopt"] = {
                "version": "2.0.0",
                "request_id": request_id,
                "savings_pct": round(
                    (1 - opt_result["optimized_tokens"] / max(opt_result["original_tokens"], 1)) * 100, 2
                ),
                "token_savings": opt_result["original_tokens"] - opt_result["optimized_tokens"],
                "original_tokens": opt_result["original_tokens"],
                "optimized_tokens": opt_result["optimized_tokens"],
                "fidelity_score": opt_result.get("fidelity_score"),
                "fidelity_passed": opt_result.get("fidelity_passed"),
                "response_fidelity": opt_result.get("response_fidelity"),
                "techniques": opt_result["techniques"],
                "cache_hit": opt_result["cache_hit"],
                "was_optimized": opt_result["optimized_tokens"] < opt_result["original_tokens"],
                "was_rolled_back": opt_result.get("was_rolled_back", False),
                "was_skipped": opt_result.get("was_skipped", False),
                "rollback_reason": opt_result.get("rollback_reason"),
                "optimization_latency_ms": round((provider_start - start_time) * 1000, 2),
                "provider_latency_ms": round(provider_latency * 1000, 2),
                "total_latency_ms": round(total_latency * 1000, 2),
                "estimated_cost_original": round(original_cost, 6),
                "estimated_cost_optimized": round(optimized_cost, 6),
                "cost_savings": round(original_cost - optimized_cost, 6),
                "provider": result.get("_provider", "unknown")
            }

            # 7. Async audit logging
            audit_entry = AuditLogEntry(
                tenant_id=tenant["tenant_id"],
                user_id=tenant["user_id"],
                request_id=request_id,
                provider=result.get("_provider", "unknown"),
                model=request.model,
                original_prompt="\n".join([f"{m.role}: {m.content}" for m in request.messages]),
                optimized_prompt=opt_result["optimized_prompt"],
                original_tokens=opt_result["original_tokens"],
                optimized_tokens=opt_result["optimized_tokens"],
                techniques=opt_result["techniques"],
                cache_hit=opt_result["cache_hit"],
                fidelity_score=opt_result.get("fidelity_score", 0.0),
                fidelity_passed=opt_result.get("fidelity_passed", False),
                was_optimized=opt_result["optimized_tokens"] < opt_result["original_tokens"],
                was_rolled_back=opt_result.get("was_rolled_back", False),
                rollback_reason=opt_result.get("rollback_reason"),
                optimization_latency_ms=(provider_start - start_time) * 1000,
                provider_latency_ms=provider_latency * 1000,
                total_latency_ms=total_latency * 1000,
                estimated_cost_original=original_cost,
                estimated_cost_optimized=optimized_cost,
                cost_savings=original_cost - optimized_cost,
                response_tokens=usage.get("completion_tokens", 0),
                finish_reason=result["choices"][0].get("finish_reason") if result.get("choices") else None,
                ip_address=http_request.client.host if http_request.client else None,
                user_agent=http_request.headers.get("user-agent")
            )

            background_tasks.add_task(services.audit_db.log_request, audit_entry)
            background_tasks.add_task(services.event_stream.emit_request, audit_entry)

            return result

        except ProviderError as e:
            logger.error(f"Provider error: {e}")
            raise HTTPException(status_code=502, detail=str(e)) from e
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error") from e

@app.get("/v1/tokenopt/stats")
async def get_stats(
    tenant: Dict = Depends(authenticate),
    hours: int = 24
):
    """Get comprehensive platform statistics."""
    start_time = datetime.now(timezone.utc) - timedelta(hours=hours)

    db_stats = await services.audit_db.get_stats(
        tenant_id=tenant["tenant_id"],
        start_time=start_time
    )

    cache_stats = await services.cache.get_stats()
    provider_stats = services.provider_router.get_all_stats()
    fidelity_stats = services.fidelity_validator.get_stats()

    return {
        "tenant_id": tenant["tenant_id"],
        "period_hours": hours,
        "database": db_stats,
        "cache": cache_stats,
        "providers": provider_stats,
        "fidelity": fidelity_stats,
        "platform": {
            "version": "2.0.0",
            "max_concurrent": services.config.MAX_CONCURRENT_REQUESTS,
            "fidelity_threshold": services.config.FIDELITY_THRESHOLD,
            "llm_judge_enabled": services.config.ENABLE_LLM_JUDGE
        }
    }

@app.get("/v1/tokenopt/rollbacks")
async def get_rollbacks(
    tenant: Dict = Depends(authenticate),
    limit: int = 100
):
    """Get recent rollbacks for investigation."""
    rollbacks = await services.audit_db.get_recent_rollbacks(
        tenant_id=tenant["tenant_id"],
        limit=limit
    )
    return {
        "tenant_id": tenant["tenant_id"],
        "rollbacks": rollbacks,
        "count": len(rollbacks)
    }

@app.post("/v1/tokenopt/validate")
async def validate_prompt(
    prompt: str,
    tenant: Dict = Depends(authenticate)
):
    """Preview optimization without API call."""
    optimizer = build_optimizer()
    messages = [ChatMessage(role="user", content=prompt)]
    result = await optimizer.optimize(messages)

    return {
        "original": prompt,
        "optimized": result["optimized_prompt"],
        "original_tokens": result["original_tokens"],
        "optimized_tokens": result["optimized_tokens"],
        "savings_pct": round((1 - result["optimized_tokens"] / max(result["original_tokens"], 1)) * 100, 2),
        "fidelity_score": result.get("fidelity_score"),
        "fidelity_passed": result.get("fidelity_passed"),
        "techniques": result["techniques"],
        "estimated_cost_savings": f"${(result['original_tokens'] - result['optimized_tokens']) * services.config.DEFAULT_TOKEN_PRICE:.6f}"
    }

if __name__ == "__main__":
    import uvicorn

    # Match the Docker default (see Dockerfile ENV PORT=8000) so running the
    # module directly and running in the container expose the same port.
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
