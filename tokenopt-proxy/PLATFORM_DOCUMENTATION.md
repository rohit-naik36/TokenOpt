# TokenOpt Enterprise Platform Documentation
## Architecture, Operations, and Compliance

**Version:** 2.0.0  
**Classification:** Internal Use  
**Owner:** Platform Engineering Team

---

## 1. Platform Architecture

### 1.1 System Overview

TokenOpt Enterprise is a transparent AI token optimization platform that sits between your applications and LLM providers (OpenAI, Azure, Anthropic, Google). It intercepts API calls, optimizes prompts to reduce token usage by 30-60%, validates that output quality is preserved, and routes requests to the best available provider.

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Your App      │────▶│  TokenOpt Proxy  │────▶│  LLM Provider   │
│  (Python/Node/  │     │                  │     │  (OpenAI/Azure/  │
│   Java/Go)      │◀────│  • Optimize      │◀────│   Anthropic)    │
│                 │     │  • Validate      │     │                 │
│                 │     │  • Route         │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │  PostgreSQL      │
                       │  Redis Cluster   │
                       │  Kafka           │
                       └──────────────────┘
```

### 1.2 Component Architecture

#### Layer 1: Integration Hub
| Component | Technology | Purpose |
|-----------|------------|---------|
| API Gateway | FastAPI + Uvicorn | OpenAI-compatible REST API |
| Authentication | JWT (HS256) | Tenant isolation, RBAC |
| Rate Limiting | Token bucket (in-memory + Redis) | Per-tenant quota enforcement |
| Load Balancing | Kubernetes Service + ALB | Traffic distribution |

#### Layer 2: Optimization Engine
| Component | Technology | Purpose |
|-----------|------------|---------|
| Semantic Compressor | Custom NLP + regex | Remove fillers, redundancies |
| Context Router | TF-IDF similarity | Relevance-based context pruning |
| Embedding Cache | Redis + SimHash | Deduplicate near-identical queries |
| Prompt Templates | Pattern matching | Pre-optimized templates for common tasks |

#### Layer 3: Quality Guardrails
| Component | Technology | Purpose |
|-----------|------------|---------|
| Fidelity Validator | sentence-transformers + OpenAI embeddings | Semantic similarity scoring |
| LLM-as-Judge | GPT-4 (sampled 5%) | Output equivalence validation |
| Shadow Testing | Async parallel calls | A/B validation with rollback |
| Auto-Rollback | Threshold-based | Revert to original on quality drop |

#### Layer 4: Provider Mesh
| Component | Technology | Purpose |
|-----------|------------|---------|
| Provider Router | httpx + HTTP/2 | Multi-provider support |
| Circuit Breaker | Custom implementation | Failover on provider outages |
| Health Monitor | Background async loop | Real-time provider status |
| Cost Optimizer | Priority-based routing | Cheapest healthy provider |

### 1.3 Data Flow

```
1. Request arrives at API Gateway
   └─▶ JWT validation → Tenant resolution → Rate limit check

2. Prompt Optimization
   └─▶ Template matching → Semantic compression → Context pruning
   └─▶ Embedding-based fidelity validation

3. Provider Selection
   └─▶ Health check → Circuit breaker check → Rate limit check
   └─▶ Route to best available provider

4. Response Processing
   └─▶ Sample 5% for LLM-as-judge response validation
   └─▶ Attach optimization metadata

5. Async Persistence
   └─▶ PostgreSQL audit log
   └─▶ Redis cache update
   └─▶ Kafka event stream
```

---

## 2. Configuration Reference

### 2.1 Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `POSTGRES_DSN` | Yes | — | PostgreSQL connection string |
| `REDIS_URL` | Yes | — | Redis connection string |
| `REDIS_CLUSTER` | No | false | Use Redis in cluster mode |
| `KAFKA_BROKERS` | No | localhost:9092 | Kafka bootstrap servers |
| `OPENAI_API_KEY` | Yes* | — | OpenAI API key |
| `AZURE_OPENAI_KEY` | No | — | Azure OpenAI API key |
| `AZURE_OPENAI_ENDPOINT` | No | — | Azure OpenAI base URL |
| `ANTHROPIC_API_KEY` | No | — | Anthropic API key |
| `GEMINI_API_KEY` | No | — | Google Gemini API key (free tier OpenAI-compatible) |
| `JWT_SECRET` | Yes | — | JWT signing secret (min 32 chars/bytes) |
| `ENCRYPTION_KEY` | Yes | — | AES-256 data encryption key |
| `FIDELITY_THRESHOLD` | No | 0.995 | Minimum fidelity score (0-1) |
| `ENABLE_LLM_JUDGE` | No | true | Enable LLM-as-judge validation |
| `ENABLE_HEADROOM` | No | true | Enable headroom smart compressor |
| `HEADROOM_TARGET_RATIO` | No | 0.5 | Target compression ratio (0.1 - 0.95) |
| `HEADROOM_MIN_TOKENS` | No | 100 | Minimum token count to trigger compression |
| `MIN_SAVINGS_PCT` | No | 2.0 | Minimum token savings percent to keep optimization |
| `REQUIRE_REAL_FIDELITY` | No | false | Refuse to boot with degraded fails-open validator |
| `USE_TIKTOKEN` | No | true | Use model-aware tiktoken tokenizer |
| `MAX_CONCURRENT_REQUESTS` | No | 100 | Request concurrency limit (min 1) |
| `REQUEST_TIMEOUT` | No | 60.0 | Upstream provider request timeout in seconds |
| `LOG_LEVEL` | No | INFO | Logging level |

*At least one LLM provider key required

### 2.2 Helm Chart Values

See `helm-chart/values.yaml` for full reference. Key values:

```yaml
# Scale
replicaCount: 3
autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 50

# Resources
resources:
  limits:
    cpu: 2000m
    memory: 2Gi

# Optimization
config:
  optimization_level: standard  # none, light, standard, aggressive
  fidelity_threshold: 0.995
  enable_shadow_testing: true
  enable_auto_rollback: true

# Persistence
persistence:
  cache:
    enabled: true
    size: 100Gi
    storageClass: gp3
```

---

## 3. Security & Compliance

### 3.1 Authentication

TokenOpt uses JWT tokens for authentication. Tokens contain:
- `tenant_id`: Organization identifier
- `sub`: User identifier
- `roles`: Array of roles (`user`, `admin`)
- `plan`: Subscription tier (`standard`, `enterprise`)

**Token generation:**
```bash
jwt encode --secret "$JWT_SECRET" --exp="+90d" '{
  "tenant_id": "engineering",
  "sub": "user@company.com",
  "roles": ["user"],
  "plan": "enterprise"
}'
```

### 3.2 Authorization

| Role | Permissions |
|------|-------------|
| `user` | Make API calls, view own stats |
| `admin` | View all tenant stats, manage rollbacks, view audit logs |

### 3.3 Encryption

| Layer | Method | Key Management |
|-------|--------|----------------|
| Data at rest (EBS) | AES-256-XTS | AWS KMS |
| Data at rest (RDS) | AES-256 | AWS KMS |
| Data at rest (Redis) | AES-256 | AWS KMS |
| Data in transit | TLS 1.3 | ACM certificates |
| Application secrets | AES-256-GCM | AWS Secrets Manager |
| Cache data | AES-256-GCM | Environment ENCRYPTION_KEY |

### 3.4 Audit Trail

Every request is logged with:
- Request/response content (truncated to 10KB)
- Optimization metadata (techniques, savings, fidelity)
- Performance metrics (latencies)
- Cost estimates
- User identity and IP address

Retention: 90 days (configurable)

### 3.5 Compliance Mappings

| Control | Implementation |
|---------|----------------|
| SOC 2 Type II | Audit logging, access controls, encryption |
| ISO 27001 | Key management, incident response procedures |
| GDPR | Data retention policies, right to deletion |
| HIPAA | Encryption at rest/transit, audit trails, BAAs with providers |

---

## 4. Operations Runbook

### 4.1 Daily Operations

#### Check Platform Health
```bash
# Quick health check
curl -f https://api.tokenopt.yourcompany.com/health

# Check all pods
kubectl get pods -n tokenopt

# Check resource usage
kubectl top pods -n tokenopt

# Review recent rollbacks
curl -H "Authorization: Bearer $ADMIN_TOKEN"   https://api.tokenopt.yourcompany.com/v1/tokenopt/rollbacks
```

#### Review Metrics Dashboard
1. Open Grafana: https://grafana.tokenopt.yourcompany.com
2. Navigate to "TokenOpt Main Dashboard"
3. Check these panels:
   - Request rate (should be within expected range)
   - Error rate (should be < 1%)
   - Fidelity score (should be > 0.99)
   - Rollback rate (should be < 2%)
   - Cache hit rate (should be > 50%)
   - Cost savings (should be positive)

### 4.2 Weekly Operations

#### Review Cost Savings
```bash
# Get weekly stats
curl -H "Authorization: Bearer $ADMIN_TOKEN"   "https://api.tokenopt.yourcompany.com/v1/tokenopt/stats?hours=168" | jq

# Expected output:
# {
#   "total_requests": 2450000,
#   "total_original_tokens": 890000000,
#   "total_optimized_tokens": 520000000,
#   "avg_fidelity": 0.9975,
#   "rollback_rate": 0.8,
#   "total_cost_savings": 12500.50
# }
```

#### Capacity Planning
```bash
# Check if HPA is scaling
kubectl get hpa -n tokenopt

# Review node utilization
kubectl top nodes

# If consistently > 70% CPU or > 80% memory:
# 1. Increase node count: terraform apply -var="node_desired_size=7"
# 2. Or increase instance size: terraform apply -var="node_instance_types=["m6i.4xlarge"]"
```

### 4.3 Monthly Operations

#### Security Review
1. Rotate JWT secrets
2. Review access logs for anomalies
3. Update provider API keys
4. Review and apply security patches

#### Database Maintenance
```bash
# Refresh materialized views
kubectl exec -it deployment/tokenopt-proxy -n tokenopt --   python -c "import asyncio; from persistence_layer_v2 import AuditDatabase; db = AuditDatabase(); asyncio.run(db.initialize()); asyncio.run(db.refresh_materialized_view())"

# Clean old partitions
kubectl exec -it deployment/tokenopt-proxy -n tokenopt --   python -c "import asyncio; from persistence_layer_v2 import AuditDatabase; db = AuditDatabase(); asyncio.run(db.initialize()); asyncio.run(db.cleanup_old_data())"
```

### 4.4 Incident Response

#### P1: Complete Outage
1. Check provider status pages
2. If provider issue: Circuit breaker should auto-failover
3. If platform issue: Check pod status, restart if needed
4. If infrastructure issue: Check AWS status page

#### P2: High Error Rate
```bash
# Check logs
kubectl logs -l app=tokenopt -n tokenopt --tail=100 | grep ERROR

# Check provider health
curl https://api.tokenopt.yourcompany.com/health | jq '.services.providers'

# Common fixes:
# - Restart unhealthy provider connections
# - Scale up if resource-constrained
# - Check for rate limiting
```

#### P3: Low Fidelity Scores
```bash
# Check recent rollbacks
curl -H "Authorization: Bearer $ADMIN_TOKEN"   https://api.tokenopt.yourcompany.com/v1/tokenopt/rollbacks | jq

# If pattern emerges:
# 1. Temporarily lower fidelity threshold
# 2. Disable aggressive optimization
# 3. Investigate specific prompt patterns causing issues
```

---

## 5. Scaling Guide

### 5.1 Horizontal Scaling

```bash
# Scale proxy replicas
kubectl scale deployment tokenopt-proxy --replicas=10 -n tokenopt

# Or update Helm values and upgrade
helm upgrade tokenopt ./helm-chart   --set replicaCount=10   --namespace tokenopt
```

### 5.2 Vertical Scaling

```bash
# Update resource limits
helm upgrade tokenopt ./helm-chart   --set resources.limits.cpu=4000m   --set resources.limits.memory=4Gi   --namespace tokenopt
```

### 5.3 Database Scaling

```bash
# Scale RDS (requires downtime for instance class change)
aws rds modify-db-instance   --db-instance-identifier tokenopt-production   --db-instance-class db.r6g.4xlarge   --apply-immediately

# Scale Redis (no downtime for ElastiCache)
aws elasticache modify-replication-group   --replication-group-id tokenopt-production   --cache-node-type cache.r6g.2xlarge   --apply-immediately
```

---

## 6. Backup & Disaster Recovery

### 6.1 Backup Procedures

#### PostgreSQL Backup
```bash
# Automated daily snapshots via RDS
# Manual snapshot before major changes:
aws rds create-db-snapshot   --db-instance-identifier tokenopt-production   --db-snapshot-identifier tokenopt-pre-upgrade-$(date +%Y%m%d)
```

#### Redis Backup
```bash
# ElastiCache automatic backups
# Manual backup:
aws elasticache create-snapshot   --replication-group-id tokenopt-production   --snapshot-name tokenopt-manual-$(date +%Y%m%d)
```

### 6.2 Disaster Recovery

| Scenario | RTO | RPO | Recovery Steps |
|----------|-----|-----|----------------|
| Single pod failure | 30s | 0 | Kubernetes auto-restart |
| Node failure | 2 min | 0 | Pod rescheduled to healthy node |
| AZ failure | 5 min | 0 | Multi-AZ RDS/Redis, pod redistribution |
| Region failure | 30 min | 5 min | Cross-region replica promotion |
| Complete data loss | 1 hour | 24 hours | Restore from RDS snapshot + Redis backup |

---

## 7. API Reference

### 7.1 Endpoints

| Method | Path | Auth | Status | Description |
|--------|------|------|--------|-------------|
| GET | `/health` | No | Active | Health check & backing service status |
| POST | `/v1/chat/completions` | JWT | Active | Chat completion with optimization (standard & stream) |
| GET | `/v1/tokenopt/stats` | JWT | Active | Platform statistics (cache, providers, fidelity, cost) |
| GET | `/v1/tokenopt/rollbacks` | JWT | Active | Recent rollback logs |
| POST | `/v1/tokenopt/validate` | JWT | Active | Preview optimization without provider call (`?prompt=...`) |
| GET | `/v1/models` | JWT | Planned | List available models from configured providers |
| POST | `/v1/embeddings` | JWT | Planned | Create embeddings with text compression |

### 7.2 Response Format

All chat completion responses include `tokenopt` metadata:

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "choices": [...],
  "usage": {...},
  "tokenopt": {
    "version": "2.0.0",
    "request_id": "uuid",
    "savings_pct": 42.5,
    "token_savings": 156,
    "original_tokens": 367,
    "optimized_tokens": 211,
    "fidelity_score": 0.9978,
    "fidelity_passed": true,
    "techniques": ["filler_removal:4", "semantic_compression"],
    "cache_hit": false,
    "was_optimized": true,
    "was_rolled_back": false,
    "optimization_latency_ms": 12.4,
    "provider_latency_ms": 234.1,
    "total_latency_ms": 246.5,
    "estimated_cost_original": 0.01101,
    "estimated_cost_optimized": 0.00633,
    "cost_savings": 0.00468,
    "provider": "openai"
  }
}
```

---

## 8. Troubleshooting Matrix

| Symptom | Likely Cause | Diagnostic Command | Fix |
|---------|-------------|-------------------|-----|
| 502 Bad Gateway | Provider down | `kubectl logs deployment/tokenopt-proxy | grep ERROR` | Check circuit breaker status, verify provider keys |
| High latency (>1s) | Resource starvation | `kubectl top pods` | Scale up replicas or increase resource limits |
| Low fidelity scores | Aggressive compression | Check rollback logs | Lower `FIDELITY_THRESHOLD`, disable aggressive mode |
| High rollback rate | Template mismatch | `kubectl logs | grep "template"` | Review and update prompt templates |
| Cache miss rate >80% | Cache too small | `kubectl exec redis -- redis-cli INFO memory` | Increase Redis memory or reduce TTL |
| Database connection errors | Connection pool exhausted | `kubectl logs | grep "connection"` | Increase `pool_size` in database config |
| Kafka lag increasing | Consumer slow | `kafka-consumer-groups.sh --describe` | Scale up worker replicas |

---

**Document Owner:** Platform Engineering  
**Review Cycle:** Monthly  
**Last Reviewed:** July 2026
