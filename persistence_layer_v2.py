"""
TokenOpt v2.0 - Production Database Persistence Layer
PostgreSQL for audit logs, Redis Cluster for distributed cache, Kafka for events.
"""

import json
import hashlib
import time
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import asyncio
import logging

logger = logging.getLogger("tokenopt.persistence")

# Database imports (with graceful degradation)
try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False
    logger.warning("asyncpg not installed. PostgreSQL features disabled.")

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("redis not installed. Redis features disabled.")

try:
    from aiokafka import AIOKafkaProducer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    logger.warning("aiokafka not installed. Kafka features disabled.")


# ============================================================
# PostgreSQL Audit Database
# ============================================================

@dataclass
class AuditLogEntry:
    """Structured audit log entry."""
    id: Optional[str] = None
    timestamp: Optional[datetime] = None
    tenant_id: str = ""
    user_id: str = ""
    request_id: str = ""

    # Request details
    provider: str = ""
    model: str = ""
    original_prompt: str = ""
    optimized_prompt: str = ""
    original_tokens: int = 0
    optimized_tokens: int = 0

    # Optimization metadata
    techniques: str = ""  # JSON array
    template_used: Optional[str] = None
    cache_hit: bool = False

    # Quality metrics
    fidelity_score: float = 0.0
    fidelity_passed: bool = False
    was_optimized: bool = False
    was_rolled_back: bool = False
    rollback_reason: Optional[str] = None

    # Performance
    optimization_latency_ms: float = 0.0
    provider_latency_ms: float = 0.0
    total_latency_ms: float = 0.0

    # Cost
    estimated_cost_original: float = 0.0
    estimated_cost_optimized: float = 0.0
    cost_savings: float = 0.0

    # Response
    response_tokens: int = 0
    finish_reason: Optional[str] = None

    # Error tracking
    error: Optional[str] = None
    error_type: Optional[str] = None

    # Compliance
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    request_headers: Optional[str] = None  # JSON


class AuditDatabase:
    """
    Production audit database with:
    - Structured schema for compliance
    - Partitioning by date for performance
    - Retention policies
    - Indexed queries for analytics
    """

    def __init__(
        self,
        dsn: str = "postgresql://tokenopt:password@localhost:5432/tokenopt",
        pool_size: int = 20,
        retention_days: int = 90
    ):
        self.dsn = dsn
        self.pool_size = pool_size
        self.retention_days = retention_days
        self._pool: Optional[asyncpg.Pool] = None
        self._initialized = False

    async def initialize(self):
        """Initialize database connection pool and schema."""
        if not ASYNCPG_AVAILABLE:
            logger.warning("PostgreSQL not available, using in-memory fallback")
            self._initialized = True
            return

        self._pool = await asyncpg.create_pool(
            self.dsn,
            min_size=5,
            max_size=self.pool_size,
            command_timeout=60
        )

        async with self._pool.acquire() as conn:
            # Create audit logs table with partitioning
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    request_id TEXT NOT NULL UNIQUE,

                    provider TEXT,
                    model TEXT,
                    original_prompt TEXT,
                    optimized_prompt TEXT,
                    original_tokens INTEGER,
                    optimized_tokens INTEGER,

                    techniques JSONB,
                    template_used TEXT,
                    cache_hit BOOLEAN DEFAULT FALSE,

                    fidelity_score REAL,
                    fidelity_passed BOOLEAN,
                    was_optimized BOOLEAN,
                    was_rolled_back BOOLEAN,
                    rollback_reason TEXT,

                    optimization_latency_ms REAL,
                    provider_latency_ms REAL,
                    total_latency_ms REAL,

                    estimated_cost_original REAL,
                    estimated_cost_optimized REAL,
                    cost_savings REAL,

                    response_tokens INTEGER,
                    finish_reason TEXT,

                    error TEXT,
                    error_type TEXT,

                    ip_address INET,
                    user_agent TEXT,
                    request_headers JSONB,

                    CONSTRAINT positive_tokens CHECK (original_tokens >= 0),
                    CONSTRAINT fidelity_range CHECK (fidelity_score BETWEEN 0 AND 1)
                ) PARTITION BY RANGE (timestamp);
            """)

            # Create partitions for current and next month
            today = datetime.utcnow()
            for i in range(3):
                month = today + timedelta(days=30*i)
                partition_name = f"audit_logs_{month.strftime('%Y_%m')}"
                start_date = month.strftime('%Y-%m-01')
                end_month = month + timedelta(days=32)
                end_date = end_month.strftime('%Y-%m-01')

                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {partition_name}
                    PARTITION OF audit_logs
                    FOR VALUES FROM ('{start_date}') TO ('{end_date}');
                """)

            # Create indexes for common queries
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_tenant_time 
                ON audit_logs (tenant_id, timestamp DESC);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_request_id 
                ON audit_logs (request_id);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_model 
                ON audit_logs (model, timestamp DESC);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_fidelity 
                ON audit_logs (fidelity_score) WHERE fidelity_passed = FALSE;
            """)

            # Create materialized view for daily aggregates
            await conn.execute("""
                CREATE MATERIALIZED VIEW IF NOT EXISTS daily_stats AS
                SELECT 
                    tenant_id,
                    DATE(timestamp) as date,
                    COUNT(*) as total_requests,
                    SUM(original_tokens) as total_original_tokens,
                    SUM(optimized_tokens) as total_optimized_tokens,
                    AVG(fidelity_score) as avg_fidelity,
                    SUM(CASE WHEN was_rolled_back THEN 1 ELSE 0 END) as rollback_count,
                    SUM(cost_savings) as total_cost_savings
                FROM audit_logs
                GROUP BY tenant_id, DATE(timestamp);
            """)

            # Create retention policy function
            await conn.execute("""
                CREATE OR REPLACE FUNCTION cleanup_old_partitions()
                RETURNS void AS $$
                DECLARE
                    partition_name TEXT;
                    cutoff_date DATE;
                BEGIN
                    cutoff_date := CURRENT_DATE - INTERVAL '%s days';

                    FOR partition_name IN
                        SELECT inhrelid::regclass::text
                        FROM pg_inherits
                        WHERE inhparent = 'audit_logs'::regclass
                    LOOP
                        IF partition_name ~ 'audit_logs_(\d{4})_(\d{2})' THEN
                            -- Extract date from partition name
                            IF to_date(
                                substring(partition_name from 'audit_logs_(\d{4})_(\d{2})'),
                                'YYYY_MM'
                            ) < cutoff_date THEN
                                EXECUTE format('DROP TABLE %I', partition_name);
                            END IF;
                        END IF;
                    END LOOP;
                END;
                $$ LANGUAGE plpgsql;
            """ % self.retention_days)

        self._initialized = True
        logger.info("Audit database initialized")

    async def log_request(self, entry: AuditLogEntry) -> str:
        """Log a request to the audit database."""
        if not ASYNCPG_AVAILABLE or not self._pool:
            # Fallback: log to stdout for development
            logger.info(f"AUDIT: {json.dumps(asdict(entry), default=str)}")
            return "logged"

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO audit_logs (
                    tenant_id, user_id, request_id, provider, model,
                    original_prompt, optimized_prompt, original_tokens, optimized_tokens,
                    techniques, template_used, cache_hit,
                    fidelity_score, fidelity_passed, was_optimized, was_rolled_back, rollback_reason,
                    optimization_latency_ms, provider_latency_ms, total_latency_ms,
                    estimated_cost_original, estimated_cost_optimized, cost_savings,
                    response_tokens, finish_reason,
                    error, error_type,
                    ip_address, user_agent, request_headers
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, $29, $30)
                RETURNING id
            """,
                entry.tenant_id, entry.user_id, entry.request_id,
                entry.provider, entry.model,
                entry.original_prompt[:10000], entry.optimized_prompt[:10000],  # Limit size
                entry.original_tokens, entry.optimized_tokens,
                json.dumps(entry.techniques) if isinstance(entry.techniques, list) else entry.techniques,
                entry.template_used, entry.cache_hit,
                entry.fidelity_score, entry.fidelity_passed,
                entry.was_optimized, entry.was_rolled_back, entry.rollback_reason,
                entry.optimization_latency_ms, entry.provider_latency_ms, entry.total_latency_ms,
                entry.estimated_cost_original, entry.estimated_cost_optimized, entry.cost_savings,
                entry.response_tokens, entry.finish_reason,
                entry.error, entry.error_type,
                entry.ip_address, entry.user_agent,
                json.dumps(entry.request_headers) if entry.request_headers else None
            )
            return str(row["id"])

    async def get_stats(
        self,
        tenant_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get aggregated statistics."""
        if not ASYNCPG_AVAILABLE or not self._pool:
            return {"error": "Database not available"}

        start_time = start_time or datetime.utcnow() - timedelta(hours=24)
        end_time = end_time or datetime.utcnow()

        async with self._pool.acquire() as conn:
            where_clause = "timestamp BETWEEN $1 AND $2"
            params = [start_time, end_time]

            if tenant_id:
                where_clause += " AND tenant_id = $3"
                params.append(tenant_id)

            row = await conn.fetchrow(f"""
                SELECT 
                    COUNT(*) as total_requests,
                    SUM(original_tokens) as total_original_tokens,
                    SUM(optimized_tokens) as total_optimized_tokens,
                    AVG(fidelity_score) as avg_fidelity,
                    SUM(CASE WHEN was_rolled_back THEN 1 ELSE 0 END) as rollback_count,
                    SUM(cost_savings) as total_cost_savings,
                    AVG(total_latency_ms) as avg_latency
                FROM audit_logs
                WHERE {where_clause}
            """, *params)

            return {
                "total_requests": row["total_requests"] or 0,
                "total_original_tokens": row["total_original_tokens"] or 0,
                "total_optimized_tokens": row["total_optimized_tokens"] or 0,
                "avg_fidelity": round(row["avg_fidelity"] or 0, 4),
                "rollback_count": row["rollback_count"] or 0,
                "rollback_rate": round((row["rollback_count"] or 0) / max(row["total_requests"] or 1, 1) * 100, 2),
                "total_cost_savings": round(row["total_cost_savings"] or 0, 4),
                "avg_latency_ms": round(row["avg_latency"] or 0, 2),
                "period": f"{start_time.isoformat()} to {end_time.isoformat()}"
            }

    async def get_recent_rollbacks(
        self,
        limit: int = 100,
        tenant_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get recent rollbacks for investigation."""
        if not ASYNCPG_AVAILABLE or not self._pool:
            return []

        async with self._pool.acquire() as conn:
            where_clause = "was_rolled_back = TRUE"
            params = []

            if tenant_id:
                where_clause += " AND tenant_id = $1"
                params.append(tenant_id)

            rows = await conn.fetch(f"""
                SELECT 
                    timestamp, request_id, model, fidelity_score,
                    rollback_reason, original_tokens, optimized_tokens
                FROM audit_logs
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT {limit}
            """, *params)

            return [dict(row) for row in rows]

    async def refresh_materialized_view(self):
        """Refresh daily stats materialized view."""
        if ASYNCPG_AVAILABLE and self._pool:
            async with self._pool.acquire() as conn:
                await conn.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY daily_stats")

    async def cleanup_old_data(self):
        """Run retention cleanup."""
        if ASYNCPG_AVAILABLE and self._pool:
            async with self._pool.acquire() as conn:
                await conn.execute("SELECT cleanup_old_partitions()")
                logger.info("Old audit partitions cleaned up")

    async def close(self):
        """Close database pool."""
        if self._pool:
            await self._pool.close()


# ============================================================
# Redis Cluster Cache
# ============================================================

class DistributedCache:
    """
    Production distributed cache with:
    - Redis Cluster support
    - Serialization compression
    - TTL management
    - Circuit breaker for cache failures
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        cluster_mode: bool = False,
        ttl_seconds: int = 3600,
        max_memory_mb: int = 2048,
        compression: bool = True
    ):
        self.redis_url = redis_url
        self.cluster_mode = cluster_mode
        self.ttl = ttl_seconds
        self.compression = compression
        self._redis: Optional[Any] = None
        self._initialized = False

        # In-memory fallback store (used when Redis is unavailable).
        # TTL is enforced lazily on read; entries are bounded by size.
        self._memory: Dict[str, Tuple[float, Any]] = {}
        self._memory_errors = 0
        self._memory_max_entries = 10000

        # Stats
        self._hits = 0
        self._misses = 0
        self._errors = 0

    async def initialize(self):
        """Initialize Redis connection."""
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available, using in-memory fallback")
            self._initialized = True
            return

        try:
            if self.cluster_mode:
                startup_nodes = [{"host": "localhost", "port": "6379"}]
                self._redis = await redis.RedisCluster(
                    startup_nodes=startup_nodes,
                    decode_responses=True,
                    skip_full_coverage_check=True
                )
            else:
                self._redis = await redis.from_url(
                    self.redis_url,
                    decode_responses=True,
                    encoding="utf-8"
                )

            # Test connection
            await self._redis.ping()
            self._initialized = True
            logger.info("Redis cache initialized")

        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            self._redis = None
            self._initialized = True  # Will use fallback

    def _make_key(self, prefix: str, data: str) -> str:
        """Create a cache key with prefix."""
        hash_val = hashlib.sha256(data.encode()).hexdigest()[:32]
        return f"tokenopt:{prefix}:{hash_val}"

    def _serialize(self, value: Any) -> str:
        """Serialize value to string."""
        json_str = json.dumps(value, default=str)
        if self.compression and len(json_str) > 1024:
            try:
                import zlib
                compressed = zlib.compress(json_str.encode())
                return f"COMPRESSED:{compressed.hex()}"
            except Exception:
                pass
        return json_str

    def _deserialize(self, value: str) -> Any:
        """Deserialize value from string."""
        if value.startswith("COMPRESSED:"):
            try:
                import zlib
                compressed = bytes.fromhex(value[11:])
                json_str = zlib.decompress(compressed).decode()
                return json.loads(json_str)
            except Exception:
                pass
        return json.loads(value)

    async def get(self, prefix: str, key_data: str) -> Optional[Any]:
        """Get value from cache."""
        if not self._redis:
            return self._memory_get(prefix, key_data)

        try:
            key = self._make_key(prefix, key_data)
            value = await self._redis.get(key)

            if value:
                self._hits += 1
                return self._deserialize(value)

            self._misses += 1
            return None

        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            self._errors += 1
            return None

    def _memory_get(self, prefix: str, key_data: str) -> Optional[Any]:
        """Read from the in-memory fallback store with TTL enforcement."""
        key = self._make_key(prefix, key_data)
        entry = self._memory.get(key)
        if entry is None:
            self._misses += 1
            return None

        expires_at, value = entry
        if time.time() > expires_at:
            self._memory.pop(key, None)
            self._misses += 1
            return None

        self._hits += 1
        return value

    async def set(
        self,
        prefix: str,
        key_data: str,
        value: Any,
        ttl: Optional[int] = None
    ):
        """Set value in cache."""
        if not self._redis:
            self._memory_set(prefix, key_data, value, ttl)
            return

        try:
            key = self._make_key(prefix, key_data)
            serialized = self._serialize(value)

            await self._redis.setex(
                key,
                ttl or self.ttl,
                serialized
            )

        except Exception as e:
            logger.warning(f"Cache set error: {e}")
            self._errors += 1

    def _memory_set(self, prefix: str, key_data: str, value: Any, ttl: Optional[int] = None):
        """Write to the in-memory fallback store (bounded, lazily expiring)."""
        if self._memory_max_entries and len(self._memory) >= self._memory_max_entries:
            # Simple bounded eviction: drop the oldest entries past their TTL.
            now = time.time()
            expired = [k for k, (exp, _) in self._memory.items() if exp <= now]
            for k in expired:
                self._memory.pop(k, None)
            if len(self._memory) >= self._memory_max_entries:
                # Still full: drop oldest by insertion (dict preserves order).
                for k in list(self._memory.keys())[: len(self._memory) - self._memory_max_entries + 1]:
                    self._memory.pop(k, None)

        key = self._make_key(prefix, key_data)
        self._memory[key] = (time.time() + (ttl or self.ttl), value)

    async def delete(self, prefix: str, key_data: str):
        """Delete value from cache."""
        if not self._redis:
            return

        try:
            key = self._make_key(prefix, key_data)
            await self._redis.delete(key)
        except Exception as e:
            logger.warning(f"Cache delete error: {e}")

    async def get_embedding(self, text: str) -> Optional[List[float]]:
        """Get cached embedding vector."""
        return await self.get("embedding", text)

    async def set_embedding(self, text: str, embedding: List[float]):
        """Cache embedding vector."""
        await self.set("embedding", text, embedding, ttl=self.ttl * 24)  # Longer TTL

    async def get_response(self, prompt: str, model: str) -> Optional[Dict]:
        """Get cached LLM response."""
        cache_key = f"{model}:{prompt}"
        return await self.get("response", cache_key)

    async def set_response(self, prompt: str, model: str, response: Dict):
        """Cache LLM response."""
        cache_key = f"{model}:{prompt}"
        await self.set("response", cache_key, response, ttl=300)  # Short TTL for responses

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "errors": self._errors,
            "hit_rate": round(self._hits / total * 100, 2) if total > 0 else 0,
            "total_requests": total,
            "redis_connected": self._redis is not None
        }

    async def close(self):
        if self._redis:
            await self._redis.close()


# ============================================================
# Kafka Event Stream
# ============================================================

class EventStreamer:
    """
    Production event streaming with Kafka.
    Used for:
    - Real-time analytics
    - Audit trail replication
    - Alerting triggers
    - Cross-region sync
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        topic: str = "tokenopt-events"
    ):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self._producer: Optional[Any] = None
        self._initialized = False

    async def initialize(self):
        """Initialize Kafka producer."""
        if not KAFKA_AVAILABLE:
            logger.warning("Kafka not available, events will be logged only")
            self._initialized = True
            return

        try:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v, default=str).encode(),
                key_serializer=lambda k: k.encode() if k else None,
                compression_type="gzip",
                batch_size=16384,
                linger_ms=10
            )
            await self._producer.start()
            self._initialized = True
            logger.info("Kafka event stream initialized")

        except Exception as e:
            logger.error(f"Kafka connection failed: {e}")
            self._producer = None
            self._initialized = True

    async def emit(
        self,
        event_type: str,
        payload: Dict[str, Any],
        key: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None
    ):
        """Emit an event to Kafka."""
        event = {
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "payload": payload
        }

        if self._producer:
            try:
                await self._producer.send(
                    self.topic,
                    value=event,
                    key=key,
                    headers=[(k, v.encode()) for k, v in (headers or {}).items()]
                )
            except Exception as e:
                logger.warning(f"Kafka emit failed: {e}")

        # Always log locally as backup
        logger.info(f"EVENT: {json.dumps(event)}")

    async def emit_request(self, audit_entry: AuditLogEntry):
        """Emit request completion event."""
        await self.emit(
            "request.completed",
            {
                "tenant_id": audit_entry.tenant_id,
                "request_id": audit_entry.request_id,
                "model": audit_entry.model,
                "provider": audit_entry.provider,
                "tokens_saved": audit_entry.original_tokens - audit_entry.optimized_tokens,
                "fidelity": audit_entry.fidelity_score,
                "rolled_back": audit_entry.was_rolled_back,
                "latency_ms": audit_entry.total_latency_ms
            },
            key=audit_entry.tenant_id
        )

    async def emit_alert(self, alert_type: str, severity: str, details: Dict):
        """Emit alert event."""
        await self.emit(
            "alert.triggered",
            {
                "alert_type": alert_type,
                "severity": severity,
                "details": details
            }
        )

    async def close(self):
        if self._producer:
            await self._producer.stop()
