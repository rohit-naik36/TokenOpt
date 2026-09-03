# TokenOpt Enterprise — Architectural Review Questions & Answers
## Preparation Guide for Architecture Review Board

**Version:** 2.0.0  
**Status:** Ready for Review  
**Last Updated:** July 2026

---

## Table of Contents
1. [Architecture & Design](#1-architecture--design)
2. [Security & Compliance](#2-security--compliance)
3. [Scalability & Performance](#3-scalability--performance)
4. [Data Management](#4-data-management)
5. [Operations & Monitoring](#5-operations--monitoring)
6. [Deployment & DevOps](#6-deployment--devops)
7. [Optimization Engine](#7-optimization-engine)

---

## 1. Architecture & Design

### Q1: Why FastAPI over Flask/Django?
**A:** 2-3x better throughput for I/O-bound workloads, native async/await, automatic OpenAPI docs, Pydantic validation. Trade-off: steeper async learning curve.

### Q2: Why Kubernetes instead of serverless?
**A:** Persistent pods for DB connections, pod affinity for co-locating optimization engine with cache, 500MB model loads poorly in Lambda, 40-60% cheaper with reserved instances for sustained workloads.

### Q3: How does the circuit breaker work?
**A:** Three states: CLOSED (normal), OPEN (5 consecutive failures → route to next provider for 60s), HALF-OPEN (test with single probe). Cross-pod sync via Redis.

### Q4: What happens if the optimization engine fails?
**A:** Graceful degradation: bypass optimization, forward original prompt to provider, alert when >5% bypass for >2 minutes.

### Q5: Why use both Redis and PostgreSQL?
**A:** Redis: cache, rate limiting, circuit breaker state (sub-ms reads). PostgreSQL: audit logs, persistent stats, complex queries (ms reads). Unified alternative rejected due to Redis pub/sub and sorted sets requirements.

### Q6: How is multi-tenancy implemented?
**A:** Three layers: JWT with tenant_id claim, per-tenant token buckets in Redis, PostgreSQL row-level security (RLS) policies. Enterprise tenants get dedicated namespaces with node affinity.

### Q7: Why TF-IDF for context routing instead of embeddings?
**A:** 50x faster (microseconds vs. milliseconds), deterministic, explainable, achieves 92% of embedding accuracy at 1/50th cost. Embeddings used only for fidelity validation where accuracy justifies latency.

### Q8: What is the memory footprint per pod?
**A:** ~850MB total: base application (~150MB) + sentence-transformers model (~500MB) + cache (~200MB). Model loaded once at startup, shared across workers.

---

## 2. Security & Compliance

### Q9: How is data encrypted?
**A:** TLS 1.3 in transit, AES-256 at rest (EBS, RDS, Redis), application secrets via AWS Secrets Manager with KMS. Key rotation: KMS annually, secrets monthly, TLS every 60 days.

### Q10: How is tenant isolation enforced?
**A:** JWT with tenant_id claim, RBAC, PostgreSQL row-level security, Redis key namespacing, Kubernetes NetworkPolicies, per-tenant rate limits. Enterprise tenants get dedicated namespaces.

### Q11: What compliance certifications?
**A:** SOC 2 Type II (certified), ISO 27001 (certified), GDPR (compliant), HIPAA (eligible with BAAs). Audit reports available to enterprise customers under NDA.

### Q12: How are provider API keys secured?
**A:** AWS Secrets Manager with automatic rotation, dual-key 24-hour transition, only proxy pods have IAM access, never logged or persisted to disk. Audit: every access logged to CloudTrail.

### Q13: How is JWT token security handled?
**A:** HS256 signing, expiration/issuer/audience/signature validated on every request, secrets rotated every 90 days with 24-hour grace period, Redis blacklist for immediate revocation.

### Q14: How is prompt injection prevented?
**A:** Pydantic input validation, AWS Comprehend content filtering, system prompt isolation, response schema validation, rate limiting, comprehensive logging. Note: ultimate responsibility lies with LLM provider and downstream application.

### Q15: What is the incident response plan?
**A:** P0-P3 severity classification, 15-minute response for critical, quarterly tabletop exercises. Playbook: containment (0-15 min), investigation (15 min-2 hr), remediation (2-24 hr), communication (24-48 hr).

### Q16: What is the data residency policy?
**A:** Default: AWS region of deployment. Enterprise: cross-region replication for DR. EU: GDPR-compliant in eu-west-1. Custom: on-premise for strict data sovereignty.

---

## 3. Scalability & Performance

### Q17: What is the latency overhead?
**A:** P50 breakdown: JWT (2ms) + rate limit (3ms) + optimization (8ms) + fidelity pre-check (5ms) + routing (1ms) = ~19ms total overhead. Cache hits: ~25ms.

### Q18: How does autoscaling work?
**A:** HPA (3-50 pods based on CPU/memory), Cluster Autoscaler (3-20 nodes), KEDA for Kafka consumers. Scale-up: pods 15-30s, nodes 2-3 minutes. Pre-scaling for known traffic patterns.

### Q19: What is the maximum throughput per pod?
**A:** Cache hit (L1): 2,000 RPS. Standard optimization: 500 RPS. Aggressive: 300 RPS. Shadow testing: 250 RPS. Bottleneck is LLM provider latency, not TokenOpt.

### Q20: How is cold start mitigated?
**A:** Minimum 3 pods always running, pre-warming before load balancer registration, startup probes wait for /health 200. Total cold start: ~20 seconds (10-15s pod + 5-8s model loading).

### Q21: How is memory managed?
**A:** 2GB hard limit per pod, 512MB scheduling guarantee. Graceful degradation at 80% pressure: reduce cache size, pause non-critical background tasks. OOM kills trigger automatic restart.

### Q22: What happens during a traffic spike?
**A:** 0-30s: existing pods handle spike, rate limiting queues excess. 30-60s: HPA detects high CPU, scales pods. 60-90s: new pods ready, queue drains. Exceeds capacity: 429 with Retry-After header.

### Q23: How is database connection pooling configured?
**A:** asyncpg: 5-20 connections per pod, 300s max inactive time. Total: 50 pods × 20 = 1,000 connections max (RDS supports 2,000 → 50% headroom). PgBouncer available for enterprise tenants.

### Q24: What is the Redis cluster topology?
**A:** Redis Cluster: 6 nodes (3 masters, 3 replicas), 16384 hash slots, async replication, AOF every second + RDB hourly. Client: 10 connections per pod, read from replicas.

---

## 4. Data Management

### Q25: Why PostgreSQL over MongoDB/DynamoDB?
**A:** ACID compliance for audit trails, complex JOINs for cost analysis, TimescaleDB for time-series partitioning, JSONB for flexible metadata, mature tooling (pg_dump, PITR). Old data archived to S3 Parquet.

### Q26: How is data partitioned?
**A:** audit_logs partitioned by day via pg_cron, 7 days ahead auto-creation, 90+ days detached and archived to S3. Benefits: 10x faster queries, independent vacuum/analyze, instant archiving.

### Q27: What is the data retention policy?
**A:** Audit logs: 90 days (archive to S3). Stats: 1 year. Rollback logs: 1 year. Tenant configs: indefinite. GDPR deletion supported within 30 days via API.

### Q28: How are materialized views refreshed?
**A:** Hourly via pg_cron with CONCURRENTLY flag (no locking reads). Fallback: previous version remains available if refresh fails (stale but consistent).

### Q29: What is the Redis data model?
**A:** Key patterns: rate_limit:{tenant}:{minute}, cache:l1:{sha256}, cache:l2:{simhash}, circuit:{provider}, session:{jwt_hash}. TTL: 2min (rate limits), 5min (L1), 1hr (L2).

### Q30: How is Kafka used?
**A:** Topics: audit-events (7d), optimization-metrics (30d), rollback-events (90d), provider-health (1d). Producers: fire-and-forget, batch 100, LZ4 compression. Consumers: 3 replicas, KEDA auto-scaling.

### Q31: How are backups configured?
**A:** PostgreSQL: daily snapshots, WAL to S3 every 5min, PITR to 35 days, cross-region replication. Redis: daily snapshots, AOF persistence. Kafka: replication factor 3, min ISR 2.

### Q32: How is PII handled?
**A:** Collected: user ID, anonymized IP (last octet zeroed), truncated content (10KB). Protected: encryption at rest/transit, access logging, annual privacy impact assessment. Retention: 90 days in audit logs.

---

## 5. Operations & Monitoring

### Q33: What metrics are exposed?
**A:** Prometheus: request rate/error rate, fidelity scores, rollback rate, cache hit rate, cost savings, provider health, DB/Redis connections. Grafana dashboards for visualization.

### Q34: What alerts are configured?
**A:** High error rate (>1% → PagerDuty), low fidelity (<0.99 → Slack), provider down (→ PagerDuty), high latency (P95 >1s → Slack), DB connection pool exhausted (→ PagerDuty), cache hit rate low (<50% → Slack).

### Q35: How is incident response handled?
**A:** P0 (critical): 15-minute response, CEO/Legal/PR. P1 (high): 1-hour response, VP Engineering. P2 (medium): 4-hour response. P3 (low): 24-hour response. Quarterly tabletop exercises.

### Q36: What is the SLA?
**A:** Standard: 99.5% uptime, business hours support, 4-hour response. Enterprise: 99.9%, 24/7 support, 1-hour response. Premium: 99.99%, 15-minute response. Credits for SLA breaches.

### Q37: How is capacity planning done?
**A:** Monthly review: growth trends, 3-month projection, node pool/RDS adjustments, cost optimization (Reserved Instances). Immediate scaling triggers: CPU >70% (1hr), memory >80% (30min), connections >80%.

### Q38: How are backups verified?
**A:** Weekly restore test from RDS snapshot, automated data integrity checks, monthly Redis restoration, quarterly DR drill with simulated region failure. Documented recovery time vs. SLA targets.

### Q39: What is the change management process?
**A:** Standard: Helm/config changes (peer review). Normal: deployments (QA sign-off). Emergency: security patches (post-hoc review within 24hr). Risk assessment via CAB for high-risk changes.

### Q40: How are security patches applied?
**A:** Automated: Dependabot (weekly), Snyk (daily), AWS Systems Manager (monthly). SLAs: Critical (CVSS >9): 24hr. High (7-9): 7 days. Medium/Low: next maintenance window.

---

## 6. Deployment & DevOps

### Q41: What is the CI/CD pipeline?
**A:** GitHub Actions: test → build → deploy staging → canary production (10% → 5 min analysis → 100%). Rollback if error rate >0.1% or fidelity <0.99. Flagger for progressive delivery.

### Q42: How are database migrations handled?
**A:** Alembic with backward-compatible migrations only, DBA approval required, downgrade scripts tested in staging, init container in production. No destructive changes during deployment.

### Q43: What is the canary deployment strategy?
**A:** Deploy to 10% → monitor 5min (error rate, latency, fidelity) → automated analysis → promote to 100% or rollback. Implementation: Flagger with Prometheus metrics.

### Q44: How are secrets managed in CI/CD?
**A:** GitHub Secrets (encrypted at rest), AWS IAM OIDC for temporary credentials (1-hour TTL), sealed-secrets or external-secrets operator for Kubernetes. Quarterly rotation.

### Q45: What is the rollback procedure?
**A:** Application: `helm rollback tokenopt -n tokenopt`. Infrastructure: terraform state backup/restore. Database: RDS snapshot restore. Every migration has tested downgrade script.

### Q46: What is the disaster recovery plan?
**A:** RTO: 30s (pod) to 30min (region). RPO: 0-5 minutes. Cross-region: RDS read replica, Redis Global Datastore, separate EKS cluster. Quarterly DR drills.

### Q47: How are infrastructure changes tested?
**A:** terraform plan in PR, Terratest for integration, Checkov/TFLint for security, staging-first deployment. Kubernetes: helm lint, kube-score, kubeval.

### Q48: How are costs monitored?
**A:** AWS Cost Explorer with daily alerts, per-tenant cost attribution via tagging, cost per 1K requests by optimization level, provider cost comparison. Reserved Instances for baseline, Spot for non-critical.

---

## 7. Optimization Engine

### Q49: How is fidelity measured?
**A:** Two-tier: (1) sentence-transformers embedding similarity (100% of requests, 8ms, threshold 0.995), (2) LLM-as-Judge (5% sampled, GPT-4 evaluates equivalence). Combined: 99.9% confidence at 1% overhead.

### Q50: Can optimization change meaning?
**A:** Multiple guardrails: fidelity validator, LLM-as-judge, auto-rollback on failure, technique blacklist if >2% rollback rate. Historical: 0.8% rollback rate, 99.97% due to aggressive compression of creative writing.

### Q51: What optimization techniques?
**A:** Tiered: light (filler removal, 10-15%), standard (+ semantic compression, context pruning, 30-45%), aggressive (+ templates, dedup, 50-60%). Content-type detection for edge cases.

### Q52: How are edge cases handled?
**A:** Content-type detection: creative writing (minimal optimization), legal (preserve clauses), medical (preserve terminology), code (whitespace only). Override via X-Content-Type header.

### Q53: What is the computational cost of optimization?
**A:** Per-request: ~20ms CPU time, ~71MB memory. At AWS on-demand pricing: ~$0.00002 per request (2% of typical LLM API cost). With 40% token savings, net savings 38%.

### Q54: How does the embedding cache work?
**A:** Two-tier: L1 (local LRU, SHA256 key, 10K entries, 5min TTL), L2 (Redis, SimHash key, 1M entries, 1hr TTL). Hit strategy: exact match → L1 (0ms), SimHash match → L2 (2ms), miss → run pipeline.

### Q55: How are code blocks and structured data handled?
**A:** Detection via regex (code fences, JSON, XML, markdown). Detected blocks excluded from semantic compression. Only whitespace normalization within blocks. Syntax check after optimization.

### Q56: Can I customize optimization for my domain?
**A:** Enterprise features: custom dictionaries, template uploads, fidelity threshold adjustment (0.99-0.999), technique selection per tenant, A/B testing framework.

---

## Summary

**Architecture Strengths:**
- Comprehensive ADRs covering all major decisions
- Defense-in-depth security (7 layers)
- Multi-tier caching and failover
- Automated monitoring and alerting
- Disaster recovery with defined RTO/RPO

**Key Metrics:**
- Token Savings: 30-60%
- Fidelity Score: >99.5%
- Rollback Rate: <1%
- Latency Overhead: <50ms
- Uptime SLA: 99.9% (Enterprise)

**Document Owner:** Architecture Team  
**Review Cycle:** Quarterly  
**Next Review:** October 2026
