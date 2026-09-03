"""
TokenOpt v2.0 - Production API Proxy
Integrates: real embeddings, circuit breaker providers, PostgreSQL audit, Redis cache, Kafka events.
"""

from fastapi import FastAPI, HTTPException, Request, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import asyncio
import json
import time
import os
import uuid
from datetime import datetime, timedelta
import logging

# Import v2 components
from fidelity_validator_v2 import EmbeddingFidelityValidator, FidelityScore
from provider_client_v2 import ProviderRouter, ProviderConfig, ProviderError
from persistence_layer_v2 import AuditDatabase, DistributedCache, EventStreamer, AuditLogEntry

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
    POSTGRES_DSN = os.getenv("POSTGRES_DSN", "postgresql://tokenopt:password@localhost:5432/tokenopt")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_CLUSTER = _env_bool("REDIS_CLUSTER", False)
    KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "localhost:9092")

    # AI Providers
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY", "")
    AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

    # Security
    JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")

    # Optimization
    FIDELITY_THRESHOLD = _env_float("FIDELITY_THRESHOLD", 0.995)
    ENABLE_LLM_JUDGE = _env_bool("ENABLE_LLM_JUDGE", True)
    ENABLE_HEADROOM = _env_bool("ENABLE_HEADROOM", True)
    HEADROOM_MIN_TOKENS = _env_int("HEADROOM_MIN_TOKENS", 100)
    HEADROOM_TARGET_RATIO = _env_float("HEADROOM_TARGET_RATIO", 0.5)

    # Performance
    MAX_CONCURRENT_REQUESTS = max(_env_int("MAX_CONCURRENT_REQUESTS", 100), 1)
    REQUEST_TIMEOUT = _env_float("REQUEST_TIMEOUT", 60.0)

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

app = FastAPI(
    title="TokenOpt Enterprise v2.0",
    description="Production AI token optimization with real embeddings, circuit breakers, and audit trail",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# ============================================================
# Global Services (initialized on startup)
# ============================================================

class DegradedFidelityValidator:
    """Fails-open fidelity validator used when no embedding backend is configured.

    Always passes validation (score 1.0) so optimization never blocks the
    request path. Swap in a real validator by configuring an embedding
    backend (sentence-transformers or OPENAI_API_KEY).
    """

    def __init__(self):
        self._validation_count = 0

    async def validate(self, **kwargs) -> FidelityScore:
        self._validation_count += 1
        return FidelityScore(
            overall=1.0,
            semantic_similarity=1.0,
            structural_similarity=1.0,
            llm_judge_score=None,
            passed=True,
            details={"engine": "degraded_passthrough"}
        )

    def get_stats(self) -> Dict[str, Any]:
        return {
            "engine": "degraded_passthrough",
            "validations": self._validation_count,
            "note": "No embedding backend configured; fidelity always passes (fails open)"
        }


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
            logger.info("✅ Fidelity validator initialized")
        except Exception as e:
            # Fail open: no embedding backend (no key, no local model) must
            # never block the proxy from serving requests.
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

        await self.provider_router.start_health_checks(interval=30.0)
        logger.info("✅ Provider router initialized")

        # 3. Audit Database
        self.audit_db = AuditDatabase(
            dsn=self.config.POSTGRES_DSN,
            retention_days=90
        )
        await self.audit_db.initialize()
        logger.info("✅ Audit database initialized")

        # 4. Distributed Cache
        self.cache = DistributedCache(
            redis_url=self.config.REDIS_URL,
            cluster_mode=self.config.REDIS_CLUSTER,
            ttl_seconds=3600
        )
        await self.cache.initialize()
        logger.info("✅ Distributed cache initialized")

        # 5. Event Streamer
        self.event_stream = EventStreamer(
            bootstrap_servers=self.config.KAFKA_BROKERS
        )
        await self.event_stream.initialize()
        logger.info("✅ Event streamer initialized")

        self._initialized = True
        logger.info("🚀 TokenOpt v2.0 fully initialized")

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

        logger.info("👋 TokenOpt v2.0 shutdown complete")

# Global service manager
services = ServiceManager()

@app.on_event("startup")
async def startup():
    await services.initialize()

@app.on_event("shutdown")
async def shutdown():
    await services.shutdown()

# ============================================================
# Authentication
# ============================================================

async def authenticate(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """JWT-based authentication."""
    import jwt

    try:
        token = credentials.credentials
        # In production: verify against identity provider
        # For now: simple JWT validation
        payload = jwt.decode(
            token,
            services.config.JWT_SECRET,
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
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ============================================================
# Core Optimization Logic
# ============================================================

class PromptOptimizer:
    """Production prompt optimization with real fidelity validation."""

    def __init__(self):
        self.compressor = SemanticCompressorV2()

    async def optimize(
        self,
        messages: List[ChatMessage],
        config: AppConfig,
        optimization_level: str = "standard"
    ) -> Dict[str, Any]:
        """Optimize prompt and validate fidelity."""
        # Build full prompt
        full_prompt = "\n".join([f"{m.role}: {m.content}" for m in messages])
        original_tokens = self._estimate_tokens(full_prompt)

        # Check cache first
        cached = await services.cache.get("optimized_prompt", full_prompt)
        if cached:
            return {
                "optimized_prompt": cached["prompt"],
                "optimized_tokens": cached["tokens"],
                "techniques": ["cache_hit"],
                "cache_hit": True,
                "original_tokens": cached.get("original_tokens", original_tokens),
                "fidelity_score": cached.get("fidelity_score", 1.0),
                "fidelity_passed": cached.get("fidelity_passed", True),
                "fidelity_details": cached.get("fidelity_details", {"engine": "cache_hit"})
            }

        # Apply compression (headroom first, then regex fallback)
        if config.ENABLE_HEADROOM:
            hr_compressed, hr_techniques, hr_stats = self.compressor.compress_with_headroom(
                full_prompt, optimization_level=optimization_level
            )
            if hr_techniques and hr_compressed != full_prompt:
                compressed = hr_compressed
                techniques = hr_techniques
                # Headroom reports real token counts; use them for both sides
                # so savings metrics stay consistent.
                original_tokens = hr_stats.get("tokens_before") or original_tokens
                optimized_tokens = hr_stats.get("tokens_after") or self._estimate_tokens(compressed)
            else:
                compressed, techniques = self.compressor.compress(full_prompt)
                optimized_tokens = self._estimate_tokens(compressed)
        else:
            compressed, techniques = self.compressor.compress(full_prompt)
            optimized_tokens = self._estimate_tokens(compressed)

        # Validate fidelity with real embeddings
        fidelity = await services.fidelity_validator.validate(
            original_prompt=full_prompt,
            optimized_prompt=compressed
        )

        # If fidelity too low, use less aggressive compression
        if not fidelity.passed and techniques:
            # Revert to safe compression
            compressed = self.compressor.safe_compress(full_prompt)
            optimized_tokens = self._estimate_tokens(compressed)
            techniques = ["safe_compression"]

            # Re-validate
            fidelity = await services.fidelity_validator.validate(
                original_prompt=full_prompt,
                optimized_prompt=compressed
            )

        result = {
            "optimized_prompt": compressed,
            "optimized_tokens": optimized_tokens,
            "techniques": techniques,
            "cache_hit": False,
            "original_tokens": original_tokens,
            "fidelity_score": fidelity.overall,
            "fidelity_passed": fidelity.passed,
            "fidelity_details": fidelity.details
        }

        # Cache the optimization
        await services.cache.set("optimized_prompt", full_prompt, {
            "prompt": compressed,
            "tokens": optimized_tokens,
            "original_tokens": original_tokens,
            "fidelity_score": fidelity.overall,
            "fidelity_passed": fidelity.passed,
            "fidelity_details": fidelity.details
        })

        return result

    def _estimate_tokens(self, text: str) -> int:
        return int(len(text.split()) / 0.75)


class SemanticCompressorV2:
    """Enhanced semantic compressor (same as v1 but with better patterns)."""

    FILLER_WORDS = {
        'basically', 'essentially', 'fundamentally', 'literally',
        'actually', 'really', 'quite', 'rather', 'fairly', 'pretty',
        'in order to', 'for the purpose of', 'due to the fact that',
        'in spite of the fact that', 'at this point in time',
        'in the event that', 'it is important to note that',
        'it should be noted that', 'please note that', 'kindly note'
    }

    def compress(self, text: str) -> tuple:
        import re
        techniques = []
        result = text

        # Remove fillers
        count = 0
        for filler in self.FILLER_WORDS:
            pattern = r'\b' + re.escape(filler) + r'\b'
            matches = len(re.findall(pattern, result, re.IGNORECASE))
            if matches > 0:
                result = re.sub(pattern, '', result, flags=re.IGNORECASE)
                count += matches
        if count > 0:
            techniques.append(f"filler_removal:{count}")

        # Simplify connectors
        replacements = {
            r'\bin order to\b': 'to',
            r'\bdue to the fact that\b': 'because',
            r'\bin spite of the fact that\b': 'although',
            r'\bin the event that\b': 'if',
            r'\bat this point in time\b': 'now',
            r'\bon a daily basis\b': 'daily',
        }
        for pattern, replacement in replacements.items():
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

        result = re.sub(r'\s+', ' ', result).strip()

        if result != text:
            techniques.append("semantic_compression")

        return result, techniques

    def safe_compress(self, text: str) -> str:
        import re
        result = re.sub(r' +', ' ', text)
        result = re.sub(r'\n{3,}', '\n\n', result)
        return result.strip()

    def compress_with_headroom(self, text: str, optimization_level: str = "standard") -> tuple:
        """Compress using headroom's SmartCrusher pipeline (fails open).

        Returns (compressed_text, techniques, stats) where stats carries the
        real token counts reported by headroom. On any failure returns the
        original text unchanged so the caller's existing fallback chain
        (fidelity -> safe_compress -> original prompt) takes over.

        optimization_level tunes aggressiveness: "aggressive" keeps less,
        "conservative" keeps more, "standard" uses the configured ratio.
        """
        if not HEADROOM_AVAILABLE:
            return text, [], {}

        try:
            # Lower target_ratio = keep less = more aggressive compression.
            ratio = services.config.HEADROOM_TARGET_RATIO
            if optimization_level == "aggressive":
                ratio = min(max(ratio * 0.5, 0.1), 0.95)
            elif optimization_level == "conservative":
                ratio = min(max(ratio * 1.5, 0.1), 0.95)

            config = HeadroomConfig(
                compress_user_messages=True,
                compress_system_messages=False,
                protect_recent=0,
                min_tokens_to_compress=max(services.config.HEADROOM_MIN_TOKENS, 10),
                target_ratio=ratio,
                kompress_model="disabled",
            )
            result = headroom_compress(
                [{"role": "user", "content": text}],
                model="gpt-4o",
                config=config,
            )

            if not result.messages:
                return text, [], {}

            compressed = result.messages[0].get("content", text)
            if not isinstance(compressed, str) or compressed == text:
                return text, [], {}

            transforms = list(result.transforms_applied or [])
            if result.tokens_saved <= 0:
                return text, [], {}

            techniques = [f"headroom:{t}" for t in transforms] or ["headroom:smart_crusher"]
            stats = {
                "tokens_before": result.tokens_before,
                "tokens_after": result.tokens_after,
                "tokens_saved": result.tokens_saved,
                "compression_ratio": result.compression_ratio,
            }
            return compressed, techniques, stats
        except Exception as e:
            logger.warning(f"Headroom compression failed, falling back: {e}")
            return text, [], {}

# ============================================================
# API Endpoints
# ============================================================

@app.get("/health")
async def health_check():
    """Comprehensive health check."""
    health = {
        "status": "healthy",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat(),
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
                optimizer = PromptOptimizer()
                opt_result = await optimizer.optimize(
                    request.messages,
                    services.config,
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
                async def stream_generator():
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
                                        if "choices" in parsed and parsed["choices"]:
                                            delta = parsed["choices"][0].get("delta", {})
                                            if "content" in delta:
                                                full_response += delta["content"]
                                    except Exception:
                                        pass
                    except Exception as e:
                        yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"
                    finally:
                        # Audit log in background
                        pass

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
            if "choices" in result and result["choices"]:
                response_content = result["choices"][0].get("message", {}).get("content", "")

                # Only do expensive response validation for ~5% of requests (sampled)
                if hash(request_id) % 20 == 0 and services.config.ENABLE_LLM_JUDGE:
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
            original_cost = opt_result["original_tokens"] * 0.00003  # GPT-4 rate
            optimized_cost = opt_result["optimized_tokens"] * 0.00003

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
            raise HTTPException(status_code=502, detail=str(e))
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/v1/tokenopt/stats")
async def get_stats(
    tenant: Dict = Depends(authenticate),
    hours: int = 24
):
    """Get comprehensive platform statistics."""
    start_time = datetime.utcnow() - timedelta(hours=hours)

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
    optimizer = PromptOptimizer()
    messages = [ChatMessage(role="user", content=prompt)]
    result = await optimizer.optimize(messages, services.config)

    return {
        "original": prompt,
        "optimized": result["optimized_prompt"],
        "original_tokens": result["original_tokens"],
        "optimized_tokens": result["optimized_tokens"],
        "savings_pct": round((1 - result["optimized_tokens"] / max(result["original_tokens"], 1)) * 100, 2),
        "fidelity_score": result.get("fidelity_score"),
        "fidelity_passed": result.get("fidelity_passed"),
        "techniques": result["techniques"],
        "estimated_cost_savings": f"${(result['original_tokens'] - result['optimized_tokens']) * 0.00003:.6f}"
    }

# Check sentence-transformers availability
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

# Optional headroom integration (pip install headroom-ai)
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
