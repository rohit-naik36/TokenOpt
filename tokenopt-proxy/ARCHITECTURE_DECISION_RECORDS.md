# TokenOpt Enterprise — Architecture Decision Records

**Version:** 2.0.0  
**Status:** Approved  
**Last Updated:** July 2026

---

## ADR-001: Use FastAPI as the API Framework

**Status:** Accepted  
**Date:** 2024-03-15  
**Deciders:** Platform Engineering Team

### Context
We needed a high-performance, async-capable web framework for the TokenOpt proxy that could handle thousands of concurrent LLM API requests with minimal overhead.

### Decision
We chose FastAPI over Flask, Django, and Node.js/Express.

### Consequences
**Positive:**
- 2-3x better throughput than Flask for I/O-bound workloads
- Native async/await support for concurrent provider calls
- Automatic OpenAPI documentation generation
- Pydantic integration for request/response validation
- Rich middleware ecosystem

**Negative:**
- Steeper learning curve for developers unfamiliar with async Python
- Debugging async code is more complex than synchronous code
- Smaller community than Django/Flask

### Alternatives Considered
- **Flask:** Simpler but synchronous by default; would require gevent for async
- **Django:** Too heavy for a proxy service; ORM not needed
- **Express.js:** Good async support but Python ecosystem preferred for ML components

---

## ADR-002: Deploy on AWS EKS (Kubernetes)

**Status:** Accepted  
**Date:** 2024-03-20  
**Deciders:** Platform Engineering, DevOps Team

### Context
We needed an orchestration platform that could handle stateful workloads, custom scheduling, and multi-cloud portability.

### Decision
We chose AWS EKS (Kubernetes) over AWS Lambda, ECS, and serverless platforms.

### Consequences
**Positive:**
- Persistent pods for database connections and model caching
- Pod affinity for co-locating optimization engine with cache
- Fine-grained resource control (CPU/memory limits)
- Multi-cloud portability (Helm charts deployable to GKE, AKS)
- Mature ecosystem (Prometheus, Grafana, cert-manager)

**Negative:**
- Higher operational complexity than serverless
- Node management overhead
- Cold start time of 20 seconds for new pods

### Alternatives Considered
- **AWS Lambda:** Cold starts incompatible with 500MB model loading
- **AWS ECS:** Simpler but less ecosystem maturity
- **Google Cloud Run:** Good for HTTP services but limited for stateful workloads

---

## ADR-003: Use PostgreSQL for Audit Storage

**Status:** Accepted  
**Date:** 2024-04-01  
**Deciders:** Data Engineering, Platform Engineering

### Context
We needed a database for audit logs that supported ACID transactions, complex queries, and time-series data.

### Decision
We chose PostgreSQL with TimescaleDB extension over MongoDB and DynamoDB.

### Consequences
**Positive:**
- ACID compliance for financial audit trails
- Complex JOINs for cost analysis across tables
- TimescaleDB for automatic partitioning and compression
- JSONB for flexible optimization metadata
- Mature backup and recovery tools

**Negative:**
- Vertical scaling limits (vs. DynamoDB's infinite scale)
- Higher operational overhead than managed NoSQL

### Alternatives Considered
- **MongoDB:** Flexible schema but weak ACID guarantees
- **DynamoDB:** Infinite scale but limited query capabilities
- **ClickHouse:** Excellent for analytics but weaker transactional support

---

## ADR-004: Use Redis for Caching and Rate Limiting

**Status:** Accepted  
**Date:** 2024-04-05  
**Deciders:** Platform Engineering

### Context
We needed a high-performance cache for optimization results and a rate limiter with sub-millisecond latency.

### Decision
We chose Redis Cluster over Memcached and in-memory caching.

### Consequences
**Positive:**
- Sub-millisecond reads for cache hits
- Sorted sets for sliding-window rate limiting (O(log N))
- Pub/sub for real-time circuit breaker state propagation
- Persistence options (AOF, RDB)

**Negative:**
- Additional infrastructure to manage
- Memory-only storage (requires sufficient RAM)

### Alternatives Considered
- **Memcached:** Simpler but no persistence or pub/sub
- **In-memory (per-pod):** Fast but no cross-pod sharing
- **DynamoDB DAX:** Managed but higher latency and cost

---

## ADR-005: Use sentence-transformers for Fidelity Validation

**Status:** Accepted  
**Date:** 2024-04-10  
**Deciders:** ML Engineering, Platform Engineering

### Context
We needed a fast, accurate method to measure semantic similarity between original and optimized prompts.

### Decision
We chose sentence-transformers (all-MiniLM-L6-v2) over OpenAI embeddings and custom models.

### Consequences
**Positive:**
- 50x faster than OpenAI embeddings (8ms vs. 400ms)
- No external API dependency for validation
- 500MB model fits in memory
- 99.5% accuracy on benchmark dataset

**Negative:**
- Model must be loaded at startup (5-8 seconds)
- Fixed vocabulary (may miss domain-specific terms)

### Alternatives Considered
- **OpenAI Embeddings:** More accurate but 50x slower and adds API cost
- **Custom Model:** Better accuracy but requires training data and maintenance
- **TF-IDF Cosine Similarity:** Fast but misses semantic meaning

---

## ADR-006: Use TF-IDF for Context Pruning

**Status:** Accepted  
**Date:** 2024-04-15  
**Deciders:** ML Engineering

### Context
We needed a fast algorithm to identify irrelevant context chunks in multi-turn conversations.

### Decision
We chose TF-IDF over embeddings and keyword matching.

### Consequences
**Positive:**
- 50x faster than embedding similarity (microseconds vs. milliseconds)
- Deterministic (no model inference)
- Explainable (term frequency scores are human-readable)
- 92% of embedding-based accuracy at 1/50th the cost

**Negative:**
- Less accurate than embeddings for semantic similarity
- Requires corpus statistics (TF-IDF vectors)

### Alternatives Considered
- **Embeddings:** More accurate but too slow for hot path
- **Keyword Matching:** Fast but misses semantic relationships

---

## ADR-007: Use JWT for Authentication

**Status:** Accepted  
**Date:** 2024-04-20  
**Deciders:** Security Team, Platform Engineering

### Context
We needed a stateless authentication mechanism for the API gateway that supported tenant isolation and RBAC.

### Decision
We chose JWT (HS256) over OAuth2, API keys, and session cookies.

### Consequences
**Positive:**
- Stateless (no database lookup per request)
- Self-contained (tenant_id, roles, plan in token)
- Easy to generate and validate
- Industry standard

**Negative:**
- Token size (~500 bytes) adds to request headers
- Cannot revoke without blacklist (Redis)
- Secret rotation requires coordination

### Alternatives Considered
- **API Keys:** Simpler but no built-in expiration or RBAC
- **OAuth2:** Overkill for internal service-to-service auth
- **Session Cookies:** Stateful, requires session store

---

## ADR-008: Use Helm for Kubernetes Deployments

**Status:** Accepted  
**Date:** 2024-05-01  
**Deciders:** DevOps Team

### Context
We needed a templating and packaging system for Kubernetes manifests.

### Decision
We chose Helm over Kustomize and raw YAML.

### Consequences
**Positive:**
- Templating for environment-specific values
- Versioned releases with rollback support
- Dependency management (charts)
- Community charts for common services

**Negative:**
- Additional abstraction layer
- Templating complexity (YAML in YAML)

### Alternatives Considered
- **Kustomize:** Simpler but less powerful templating
- **Raw YAML:** No templating, duplication across environments
- **Pulumi:** More powerful but steeper learning curve

---

## ADR-009: Use Terraform for Infrastructure

**Status:** Accepted  
**Date:** 2024-05-05  
**Deciders:** DevOps Team

### Context
We needed infrastructure-as-code for AWS resources (EKS, RDS, ElastiCache, VPC).

### Decision
We chose Terraform over CloudFormation and Pulumi.

### Consequences
**Positive:**
- Multi-cloud support (AWS, GCP, Azure)
- Rich module ecosystem
- State management with locking (S3 + DynamoDB)
- Plan/apply workflow for safe changes

**Negative:**
- State file management complexity
- HCL learning curve
- Drift detection challenges

### Alternatives Considered
- **CloudFormation:** AWS-native but vendor lock-in
- **Pulumi:** More expressive (Python/TypeScript) but newer ecosystem
- **AWS CDK:** Good for AWS-only but Terraform more mature

---

## ADR-010: Use Prometheus and Grafana for Monitoring

**Status:** Accepted  
**Date:** 2024-05-10  
**Deciders:** SRE Team, Platform Engineering

### Context
We needed a monitoring stack for metrics collection, visualization, and alerting.

### Decision
We chose Prometheus + Grafana over Datadog and New Relic.

### Consequences
**Positive:**
- Open-source (no per-host licensing)
- Native Kubernetes integration
- Powerful query language (PromQL)
- Rich visualization capabilities
- Alertmanager for multi-channel alerting

**Negative:**
- Self-hosted (operational overhead)
- Long-term storage requires additional setup (Thanos/Cortex)

### Alternatives Considered
- **Datadog:** Easier setup but expensive at scale ($15/host/month)
- **New Relic:** Good APM but costly for high cardinality metrics
- **CloudWatch:** AWS-native but limited query capabilities

---

**Document Owner:** Architecture Team  
**Review Cycle:** Quarterly  
**Last Updated:** July 2026
