# TokenOpt Enterprise — Software Development Team Q&A
## Comprehensive Questions & Answers for Engineering Teams

**Version:** 2.0.0
**Audience:** Software Engineers, DevOps, SREs, QA, Security, Product Managers
**Last Updated:** July 2026

---

## Table of Contents
1. Architecture & Design
2. Integration & API
3. Optimization Engine
4. Quality & Validation
5. Security & Compliance
6. Performance & Scaling
7. Operations & Monitoring
8. Deployment & DevOps
9. Data & Persistence
10. Business & Product
11. Troubleshooting
12. Development & Testing

---

## 1. Architecture & Design

### Q1.1: What is TokenOpt's core value proposition?
**Answer:** TokenOpt is a transparent AI token optimization platform that intercepts LLM API calls, reduces token usage by 30-60% through semantic compression and context pruning, validates output quality is preserved using embedding-based fidelity scoring and LLM-as-judge validation, and routes requests to the most cost-effective available provider. It acts as a transparent proxy — applications send standard OpenAI-compatible requests and receive standard responses with optimization metadata attached.

### Q1.2: Why was FastAPI chosen over Flask/Django/Express?
**Answer:** Several factors drove this decision:
- Performance: FastAPI's async/await support and Starlette foundation provide 2-3x better throughput than Flask for I/O-bound workloads like LLM proxying
- Type Safety: Pydantic integration provides automatic request/response validation and OpenAPI documentation generation
- Standards Compliance: Native OpenAPI/Swagger support makes it trivial to maintain the OpenAI-compatible API contract
- Developer Experience: Auto-generated interactive docs, type hints, and modern Python syntax reduce onboarding time
- Ecosystem: Rich middleware ecosystem for auth, rate limiting, and observability

Trade-off: FastAPI has a steeper learning curve for developers unfamiliar with async Python, and debugging async code can be more complex than synchronous Flask.

### Q1.3: Why Kubernetes instead of serverless (Lambda/Cloud Run)?
**Answer:** While serverless offers simplicity, Kubernetes was chosen because:
- Stateful Workloads: Redis and PostgreSQL connections benefit from persistent pods
- Custom Scheduling: Pod affinity rules ensure optimization engine and cache are co-located
- Resource Control: Fine-grained CPU/memory limits prevent noisy-neighbor issues during traffic spikes
- Complex Dependencies: The optimization engine requires sentence-transformers models loaded in memory (~500MB), which cold-start poorly in serverless
- Cost Predictability: Reserved instances on EKS are 40-60% cheaper than on-demand Lambda for sustained workloads >1000 RPM
- Multi-cloud Portability: Helm charts can deploy to GKE, AKS, or on-prem clusters

Mitigation: We use KEDA for event-driven scaling of background workers, giving us serverless-like autoscaling for Kafka consumers.

### Q1.4: Why PostgreSQL instead of MongoDB/DynamoDB for audit logs?
**Answer:** PostgreSQL was selected for audit storage because:
- ACID Compliance: Financial audit trails require transactional guarantees that NoSQL databases struggle with
- Complex Queries: Weekly cost analysis requires JOINs across audit_logs, optimization_stats, and tenant_configs tables
- Time-Series Extensions: TimescaleDB extension provides automatic partitioning and compression for time-series audit data
- JSON Support: Native JSONB columns store flexible optimization metadata while maintaining relational structure
- Mature Tooling: pg_dump, logical replication, and Point-in-Time Recovery (PITR) are battle-tested

Scaling Strategy: Data older than 90 days is automatically archived to S3 via pg_cron + aws_s3 extensions, with Parquet format for Athena querying.

### Q1.5: How does the circuit breaker pattern work for provider failover?
**Answer:** The circuit breaker operates in three states:

1. CLOSED (Normal): Requests flow to the provider. Failure count is tracked per 30-second window.
2. OPEN (Failing): After 5 consecutive failures or 50% error rate, the breaker opens. All requests are routed to the next healthy provider for 60 seconds.
3. HALF-OPEN (Testing): After the cooldown, a single probe request is sent. If it succeeds, the breaker closes; if it fails, it reopens for another 60 seconds.

Implementation: Custom asyncio-based circuit breaker using an in-memory state machine with Redis-backed state for cross-pod synchronization. Each provider maintains independent breaker state.

### Q1.6: What happens if the optimization engine itself fails?
**Answer:** The system implements graceful degradation:
1. Detection: Health checks monitor optimization engine latency and error rate
2. Bypass: If optimization fails or exceeds 500ms timeout, the original (unoptimized) prompt is forwarded to the provider
3. Fallback: If the fidelity validator is down, prompts are still optimized but marked with fidelity_passed: null and was_optimized: true
4. Alerting: PagerDuty alert fires when >5% of requests bypass optimization for >2 minutes
5. Recovery: Auto-restart via Kubernetes liveness probes; stateless design allows instant pod replacement

Key Principle: The platform never blocks a user request due to optimization failures — it falls back to pass-through mode.

### Q1.7: Why use both Redis and PostgreSQL? Couldn't we use just one?
**Answer:** They serve fundamentally different purposes:

Aspect | Redis | PostgreSQL
Primary Use | Cache, session store, rate limiting counters | Audit logs, persistent stats, tenant configs
Data Durability | Optional (AOF every second) | ACID transactions, WAL
Query Complexity | Key-value, simple structures | Complex JOINs, aggregations, window functions
Performance | Sub-millisecond reads | Millisecond-range reads
Data Size | Hot data only (~100GB) | All historical data (TBs)

Unified Alternative Considered: Using PostgreSQL for everything with pg_bouncer for connection pooling. Rejected because Redis's pub/sub is used for real-time circuit breaker state propagation, and its sorted sets power the sliding-window rate limiter with O(log N) complexity.

### Q1.8: How is multi-tenancy implemented?
**Answer:** Three isolation layers:

1. Authentication Layer: JWT tokens contain tenant_id claim. All requests are scoped to this tenant.
2. Rate Limiting: Per-tenant token buckets in Redis (key format: rate_limit:{tenant_id}:{minute})
3. Data Isolation: PostgreSQL row-level security (RLS) policies ensure SELECT * FROM audit_logs only returns rows where tenant_id = current_setting('app.current_tenant')
4. Resource Quotas: Kubernetes ResourceQuotas per namespace for enterprise tenants with dedicated namespaces

Shared vs. Dedicated: Standard plan tenants share the main namespace with RLS. Enterprise tenants get dedicated namespaces with node affinity to specific node pools.

### Q1.9: Why TF-IDF for context routing instead of embeddings?
**Answer:** TF-IDF was chosen for context pruning because:
- Speed: TF-IDF similarity computation is 50x faster than embedding cosine similarity (microseconds vs. milliseconds)
- Determinism: No model inference required, making it suitable for the hot path of every request
- Explainability: Easy to debug why a context chunk was pruned (term frequency scores are human-readable)
- Sufficient Accuracy: For the specific task of "which context chunks are most relevant to this query," TF-IDF achieves 92% of embedding-based accuracy at 1/50th the cost

Embedding Usage: Embeddings are used for the fidelity validator (post-optimization quality check) and cache deduplication, where the extra accuracy justifies the latency cost.

### Q1.10: What is the memory footprint of the optimization engine?
**Answer:** Per pod:
- Base Application: ~150MB (FastAPI, httpx, asyncpg)
- Sentence Transformers Model: ~500MB (all-MiniLM-L6-v2 loaded in memory)
- Cache: ~200MB (Redis client connection pool, local LRU cache)
- Total: ~850MB per pod

Optimization: Model is loaded once at startup and shared across all workers via multiprocessing. For aggressive memory constraints, the model can be offloaded to a separate "fidelity service" pod, reducing the proxy pod to ~200MB.

---

## 2. Integration & API

### Q2.1: How do I migrate my existing OpenAI integration to TokenOpt?
**Answer:** Three-line change:

Before (Direct OpenAI):
  import openai
  openai.api_key = "sk-..."
  response = openai.ChatCompletion.create(model="gpt-4", messages=[...])

After (TokenOpt):
  import openai
  openai.api_base = "https://api.tokenopt.yourcompany.com/v1"  # Change 1
  openai.api_key = "YOUR_TOKENOPT_JWT_TOKEN"                   # Change 2
  response = openai.ChatCompletion.create(model="gpt-4", messages=[...])
  print(response.tokenopt.savings_pct)  # Change 3

Compatibility: All OpenAI SDK methods work without modification. The tokenopt field is additive — existing code ignoring it continues to work.

### Q2.2: Do I need to change my prompt engineering practices?
**Answer:** Generally no, with these caveats:
- System Prompts: These are preserved verbatim — they define behavior and should not be compressed
- Few-Shot Examples: TokenOpt automatically detects and preserves in-context learning examples
- Structured Output (JSON/XML): The semantic compressor recognizes structured formats and avoids breaking syntax
- Chain-of-Thought: If the prompt explicitly requests step-by-step reasoning, the optimizer adds a "preserve reasoning" flag

Best Practice: Use the /v1/tokenopt/validate endpoint to preview how your specific prompts will be optimized before going live.

### Q2.3: What happens if TokenOpt is down? Can I fall back to direct provider calls?
**Answer:** Yes, implement a fallback pattern using tenacity for retry logic. Try TokenOpt first, then fallback to direct provider on APIError. TokenOpt itself implements provider failover, so a TokenOpt outage is distinct from a provider outage.

### Q2.4: How do streaming responses work?
**Answer:** TokenOpt supports Server-Sent Events (SSE) streaming:
1. Optimization: The full prompt is optimized before the first chunk is sent (adds ~10-50ms to time-to-first-token)
2. Fidelity Validation: For streaming, fidelity is checked on the complete response after the stream closes
3. Metadata: The tokenopt object is appended as the final SSE event with data: [DONE] format extended to include metadata

### Q2.5: Can I disable optimization for specific requests?
**Answer:** Yes, three methods:
1. Header: X-TokenOpt-Optimization: none
2. Query Parameter: ?optimization=none
3. Per-tenant config: Set optimization_level: none in tenant settings

Use Cases: Legal/compliance prompts, creative writing, debugging scenarios.

### Q2.6: What SDKs are supported?
**Answer:** Any HTTP client that can call OpenAI's API:
- OpenAI Python (Full)
- OpenAI Node.js (Full)
- LangChain (Full)
- LlamaIndex (Full)
- HTTP/REST (Full)
- cURL (Full)

Custom SDK: We provide a lightweight tokenopt-client Python package.

### Q2.7: How are API keys managed?
**Answer:** Two-tier system:
1. TokenOpt JWT Tokens: Issued by your organization's TokenOpt admin. Contain tenant_id, roles, and plan.
2. Provider API Keys: Stored in Kubernetes secrets and AWS Secrets Manager. TokenOpt uses these to call providers.

Rotation: JWT tokens every 90 days; Provider keys monthly with zero-downtime dual-key rotation.

### Q2.8: What is the latency overhead of TokenOpt?
**Answer:** P50 breakdown:
- JWT validation: 2ms
- Rate limit check: 3ms
- Prompt optimization: 8ms
- Fidelity pre-check: 5ms
- Provider routing: 1ms
- Total overhead: ~19ms
- Provider latency (GPT-4): ~300ms
- Total request: ~319ms

For cache hits, total latency is ~25ms.

### Q2.9: Can I use my own LLM provider accounts?
**Answer:** Yes, three models:
1. Bring Your Own Keys (BYOK): You provide API keys, TokenOpt routes through them
2. TokenOpt Managed: TokenOpt provides pooled provider access at negotiated rates
3. Hybrid: Use BYOK for primary provider, TokenOpt managed as failover

### Q2.10: How are rate limits handled?
**Answer:** Two-level rate limiting:
1. TokenOpt Level: Per-tenant token bucket. Default: 1000 RPM standard, 10000 RPM enterprise
2. Provider Level: TokenOpt tracks provider rate limits and implements token bucket smoothing

Headers: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset


---

## 3. Optimization Engine

### Q3.1: What optimization techniques are used?
**Answer:** Tiered approach based on optimization_level:

Level | Techniques | Avg Savings | Risk
none | None | 0% | None
light | Filler removal, whitespace normalization | 10-15% | Minimal
standard | + Semantic compression, context pruning | 30-45% | Low
aggressive | + Template substitution, aggressive dedup | 50-60% | Medium

Technique Details:
- Filler Removal: Removes hedging words ("I think", "perhaps", "it seems"), redundant adjectives, and polite fluff
- Semantic Compression: Replaces verbose phrases with concise equivalents ("due to the fact that" -> "because")
- Context Pruning: Uses TF-IDF to remove irrelevant historical context chunks while preserving conversation coherence
- Template Matching: Pre-optimized templates for common patterns (summarization, extraction, classification)
- Deduplication: SimHash-based near-duplicate detection across cache and conversation history

### Q3.2: How does the semantic compressor work?
**Answer:** A hybrid NLP pipeline:
1. Syntactic Analysis: spaCy dependency parsing identifies removable clauses
2. Lexical Substitution: WordNet + custom thesaurus maps verbose terms to concise equivalents
3. Redundancy Detection: Sentence-BERT embeddings identify semantically redundant sentences
4. Structure Preservation: Regex guards prevent breaking JSON, XML, markdown, or code blocks
5. Domain Adaptation: Per-tenant custom dictionaries learned from historical optimizations

Example:
  Original: "I would like to request that you please provide me with a detailed explanation of the various different methods that can be used to optimize token usage in large language model applications."
  Optimized: "Explain methods to optimize token usage in LLM applications."
  Savings: 87% (47 tokens -> 9 tokens)

### Q3.3: What is context pruning and when is it triggered?
**Answer:** Context pruning removes irrelevant historical messages from multi-turn conversations.

Trigger Conditions:
- Conversation exceeds 10 messages
- Total context tokens exceed 50% of model's context window
- TF-IDF similarity between latest query and historical chunks < 0.3

Algorithm:
1. Split conversation into chunks (system prompt, user messages, assistant responses)
2. Compute TF-IDF vectors for each chunk and the latest query
3. Rank chunks by cosine similarity to query
4. Retain top N chunks that fit within 70% of context window
5. Always preserve system prompt and most recent 2 exchanges

Safety: Pruning is disabled if the conversation contains explicit references to earlier context.

### Q3.4: How are prompt templates managed?
**Answer:** Template system:
1. Pattern Detection: Regex patterns identify common prompt structures
2. Template Library: 200+ pre-optimized templates covering summarization, extraction, classification, code generation, Q&A
3. Custom Templates: Enterprise tenants can upload custom templates via API
4. A/B Testing: New templates are shadow-tested against the general compressor; adoption requires >0.995 fidelity

### Q3.5: Can optimization introduce hallucinations or change meaning?
**Answer:** Multiple guardrails prevent this:
1. Fidelity Validator: sentence-transformers compute semantic similarity between original and optimized prompts. Threshold: 0.995
2. LLM-as-Judge: 5% of requests are sent to GPT-4 with both original and optimized prompts; GPT-4 judges output equivalence
3. Auto-Rollback: If fidelity < threshold or LLM judge disagrees, the original prompt is used
4. Technique Blacklist: Techniques that cause rollbacks >2% of the time are automatically disabled for that tenant
5. Human Review: Weekly sampling of rollbacks for pattern analysis

Historical Data: After 10M+ optimized requests, the rollback rate is 0.8%, and 99.97% of rollbacks are due to aggressive compression of creative writing prompts (now handled by content-type detection).

### Q3.6: How does the embedding cache work?
**Answer:** Two-tier caching:
1. L1 Cache (Local LRU): Per-pod in-memory cache. Key: SHA256 of prompt text. Value: optimization result. Size: 10,000 entries (~50MB). TTL: 5 minutes.
2. L2 Cache (Redis): Cross-pod shared cache. Key: SimHash of prompt. Value: optimization result + fidelity score. Size: 1M entries. TTL: 1 hour.

Cache Hit Strategy:
- Exact match -> L1 hit (0ms overhead)
- SimHash match -> L2 hit (2ms Redis roundtrip)
- Miss -> Run optimization pipeline

Invalidation: Cache entries are invalidated when templates are updated or fidelity thresholds are changed.

### Q3.7: What is SimHash and why is it used?
**Answer:** SimHash is a locality-sensitive hashing algorithm that generates similar hashes for similar inputs.

Use Case: Two prompts like "Explain quantum computing" and "Explain quantum computing briefly" should share a cache entry despite minor differences.

Properties:
- 64-bit hash generated from token n-grams
- Hamming distance < 3 indicates near-duplicate
- Collision rate: <0.01% for natural language prompts
- Computation: O(n) where n = token count

Alternative Considered: MinHash. Rejected because SimHash provides better granularity for short prompts (<50 tokens).

### Q3.8: How are code blocks and structured data handled?
**Answer:** Special handling for non-natural-language content:
1. Detection: Regex patterns identify code fences, JSON blocks, XML tags, markdown tables
2. Preservation: Detected blocks are excluded from semantic compression
3. Optimization: Within code blocks, only whitespace normalization and comment removal (if aggressive) are applied
4. Validation: After optimization, a syntax check ensures structure is intact

### Q3.9: Can I customize optimization for my domain?
**Answer:** Yes, enterprise features include:
1. Custom Dictionaries: Upload domain-specific term mappings
2. Template Uploads: Define custom prompt patterns and optimized equivalents
3. Fidelity Threshold Adjustment: Per-tenant threshold tuning (0.99-0.999)
4. Technique Selection: Enable/disable specific techniques per tenant
5. A/B Testing Framework: Test custom optimizations against baseline

### Q3.10: What is the computational cost of optimization?
**Answer:** Per-request compute breakdown:

Operation | CPU Time | Memory
Tokenization | 1ms | 2MB
Filler removal | 2ms | 1MB
Semantic compression | 4ms | 5MB
Context pruning | 3ms | 3MB
Embedding generation | 8ms | 50MB (model)
Fidelity validation | 2ms | 10MB
Total | ~20ms | ~71MB

Cost: At AWS on-demand pricing for m6i.2xlarge, optimization costs ~$0.00002 per request (2% of typical LLM API cost). With 40% token savings, net savings are 38%.

---

## 4. Quality & Validation

### Q4.1: How is fidelity measured?
**Answer:** Two-tier validation:

Tier 1: Embedding Similarity (100% of requests)
- Generate embeddings for original and optimized prompts using sentence-transformers (all-MiniLM-L6-v2)
- Compute cosine similarity
- Threshold: 0.995 (configurable)
- Latency: ~8ms

Tier 2: LLM-as-Judge (5% sampled requests)
- Send both original and optimized prompts to GPT-4
- Ask GPT-4: "Do these two prompts produce functionally equivalent outputs? Answer YES/NO"
- If NO, trigger rollback and alert
- Latency: ~500ms (async, doesn't block response)

Why Two Tiers: Embedding similarity is fast but can miss subtle semantic shifts. LLM-as-Judge is slow but accurate. The combination provides 99.9% confidence at 1% overhead.

### Q4.2: What happens when fidelity validation fails?
**Answer:** Automated response:
1. Immediate: The original (unoptimized) prompt is sent to the provider
2. Logging: Failure is logged with original prompt, optimized prompt, and fidelity score
3. Alerting: If failure rate >2% in 5 minutes, PagerDuty alert fires
4. Analysis: Daily automated analysis identifies patterns
5. Remediation: Failing techniques are automatically disabled for affected tenants
6. Learning: Failed cases are added to the training set for model improvement

### Q4.3: How is output quality preserved, not just prompt fidelity?
**Answer:** Prompt fidelity is a proxy for output quality, but we validate both:
1. Prompt Fidelity: Ensures the optimized prompt asks the same question
2. Output Sampling: 5% of responses are compared using embedding similarity of outputs, BLEU/ROUGE scores, and GPT-4 judge
3. User Feedback Loop: X-TokenOpt-Feedback: poor header allows users to flag quality issues
4. Regression Testing: Weekly test suite of 1000 benchmark prompts across domains

### Q4.4: What is shadow testing?
**Answer:** Shadow testing sends both original and optimized prompts to the provider in parallel:
  Request --> TokenOpt
              |-- Original Prompt --> Provider --> Response A (returned to user)
              |-- Optimized Prompt --> Provider --> Response B (discarded, logged)

Purpose: Validate that optimized prompts produce equivalent outputs without risking user experience.
Configuration: Enabled per-tenant via enable_shadow_testing: true. Sampling rate: 1% (configurable).

### Q4.5: How are edge cases handled (creative writing, legal, medical)?
**Answer:** Content-type detection routes prompts to appropriate handling:

Content Type | Detection Method | Optimization Strategy
Creative Writing | Style metrics, sentiment variance | Minimal optimization (light level)
Legal | Keyword matching ("pursuant", "hereinafter") | Disable filler removal, preserve all clauses
Medical | UMLS term detection | Disable semantic compression, preserve terminology
Code | AST parsing, syntax detection | Whitespace only, preserve structure
Technical | Jargon density, acronym count | Conservative compression, preserve precision

Override: Users can force content type via X-Content-Type: legal header.

### Q4.6: What is the false positive rate for fidelity validation?
**Answer:**
- Embedding Similarity: <0.1% false positives
- LLM-as-Judge: <0.5% false positives
- Combined System: <0.05% false positives
- False Negative Rate (missed quality issues): <0.01%

### Q4.7: How do you handle prompts with multiple languages?
**Answer:**
1. Language Detection: fastText language identification on prompt text
2. Model Selection: Multi-language sentence-transformers model for non-English prompts
3. Technique Adaptation: Some techniques are language-specific; only enabled for supported languages
4. Supported Languages: English (primary), Spanish, French, German, Chinese, Japanese, Korean

### Q4.8: What happens with very short prompts (<20 tokens)?
**Answer:** Short prompts are generally not optimized because:
- Diminishing Returns: 20 tokens -> 15 tokens saves $0.0001, not worth the compute
- Risk: Short prompts have higher relative impact from any change
- Performance: Cache hit rate is higher for short prompts anyway

Rule: Prompts <30 tokens bypass optimization and go straight to provider. This applies to ~40% of chat requests.

### Q4.9: How is the LLM-as-Judge prompt structured?
**Answer:**
  You are an expert evaluator of prompt equivalence.
  Original Prompt: {original_prompt}
  Optimized Prompt: {optimized_prompt}
  Task: Determine if the optimized prompt preserves the exact same intent, constraints, and expected output format as the original prompt.
  Answer with EXACTLY one word: YES or NO.
  YES means: A competent LLM would produce functionally equivalent outputs for both prompts.
  NO means: The optimized prompt omits important constraints, changes the expected output format, or alters the core intent.

Calibration: GPT-4's judgment is calibrated against a human-labeled dataset of 10,000 prompt pairs (Cohen's kappa = 0.91).

### Q4.10: Can users provide feedback on optimization quality?
**Answer:** Yes, three mechanisms:
1. Header Feedback: X-TokenOpt-Feedback: poor in subsequent request
2. API Endpoint: POST /v1/tokenopt/feedback with request_id and rating
3. Dashboard: Grafana annotation with request_id and comment

Response to Feedback:
- Immediate: Flagged request is reviewed by LLM-as-Judge
- Short-term: If pattern emerges, technique is disabled for tenant
- Long-term: Feedback is incorporated into monthly model retraining


---

## 5. Security & Compliance

### Q5.1: How is data encrypted?
**Answer:** Encryption at multiple layers:

Layer | Method | Key Management
Data in transit (client->TokenOpt) | TLS 1.3 | Let's Encrypt / ACM
Data in transit (TokenOpt->Provider) | TLS 1.3 | Provider-managed
Data at rest (EBS) | AES-256-XTS | AWS KMS
Data at rest (RDS) | AES-256 | AWS KMS
Data at rest (Redis) | AES-256 | AWS KMS
Application secrets | AES-256-GCM | AWS Secrets Manager
Cache data | AES-256-GCM | Environment ENCRYPTION_KEY

Key Rotation:
- KMS keys: Automatic annual rotation
- Application secrets: Manual rotation via Secrets Manager with dual-key period
- TLS certificates: Auto-renewal via cert-manager every 60 days

### Q5.2: Does TokenOpt store my prompts and responses?
**Answer:** Yes, with these constraints:

What is stored:
- Request/response content (truncated to 10KB)
- Optimization metadata (techniques used, savings, fidelity)
- Performance metrics (latencies)
- Cost estimates
- User identity and IP address

Retention: 90 days (configurable per tenant)

Access:
- Tenant admins can view their own audit logs via API
- Platform admins can view all logs for support/debugging
- Raw logs are never used for model training without explicit consent

Deletion: GDPR right-to-deletion supported via DELETE /v1/tokenopt/audit endpoint.

### Q5.3: How is tenant isolation enforced?
**Answer:** Defense in depth:
1. Authentication: JWT tokens with tenant_id claim
2. Authorization: RBAC with roles (user, admin)
3. Database: Row-level security (RLS) policies in PostgreSQL
4. Cache: Redis key namespacing (tenant:{tenant_id}:key)
5. Network: NetworkPolicies restrict cross-namespace traffic
6. Rate Limiting: Per-tenant quotas prevent resource exhaustion attacks
7. Encryption: Per-tenant encryption keys for sensitive data (enterprise feature)

### Q5.4: What compliance certifications does TokenOpt support?
**Answer:**

Certification | Status | Implementation
SOC 2 Type II | Certified | Audit logging, access controls, encryption
ISO 27001 | Certified | ISMS, risk assessment, incident response
GDPR | Compliant | Data retention, right to deletion, DPAs
HIPAA | Eligible | Encryption, audit trails, BAAs with providers
PCI DSS | N/A | TokenOpt does not process payment card data

Audit Reports: Available to enterprise customers under NDA.

### Q5.5: How are provider API keys secured?
**Answer:**
1. Storage: AWS Secrets Manager with automatic rotation
2. Access: Only the TokenOpt proxy pods have IAM roles to read secrets
3. Memory: Keys are loaded into memory at startup, never logged or persisted to disk
4. Rotation: Dual-key rotation — new key is added, old key is phased out over 24 hours
5. Audit: Every secret access is logged to CloudTrail
6. Encryption: Secrets are encrypted with AWS KMS customer-managed keys

### Q5.6: Can TokenOpt operate in a VPC without internet access?
**Answer:** Yes, via VPC Endpoints:
- AWS Services: VPC endpoints for ECR, Secrets Manager, CloudWatch, S3
- LLM Providers: Requires NAT Gateway or PrivateLink for provider APIs
- Alternative: Deploy TokenOpt in a public subnet with strict Security Groups, while application servers remain in private subnets

Air-Gapped Option: For fully air-gapped environments, TokenOpt can route to on-prem LLMs (e.g., self-hosted Llama, Mistral) instead of cloud providers.

### Q5.7: How is JWT token security handled?
**Answer:**
1. Signing: HS256 with 48-character random secret
2. Validation: Expiration, issuer, audience, and signature verified on every request
3. Rotation: Secrets rotated every 90 days; old secrets accepted for 24-hour grace period
4. Storage: Never stored in logs or databases
5. Scope: Tokens are scoped to tenant_id and roles; no global admin tokens
6. Revocation: Token blacklist in Redis for immediate revocation

### Q5.8: What is the incident response plan for security breaches?
**Answer:**

Detection: GuardDuty, WAF logs, and anomaly detection on audit logs

Response Playbook:
1. Containment (0-15 min): Isolate affected pods, revoke compromised tokens, rotate secrets
2. Investigation (15 min-2 hr): Forensic analysis of logs, identify scope of breach
3. Remediation (2-24 hr): Patch vulnerabilities, restore from clean backups
4. Communication (24-48 hr): Notify affected tenants per GDPR requirements
5. Post-Incident (1-2 weeks): Root cause analysis, process improvements

Tabletop Exercises: Quarterly simulations of data breach, DDoS, and insider threat scenarios.

### Q5.9: How is prompt injection prevented?
**Answer:**
1. Input Validation: Pydantic schemas enforce expected message structure
2. Content Filtering: AWS Comprehend detects toxic/jailbreak attempts
3. Prompt Separation: System prompts are isolated from user content
4. Output Validation: Response structure is validated against expected schema
5. Rate Limiting: Per-user limits prevent brute-force injection attempts
6. Logging: All requests are logged for forensic analysis

Note: TokenOpt is a proxy, not the LLM itself. Ultimate responsibility for prompt injection prevention lies with the LLM provider and the downstream application.

### Q5.10: What is the data residency policy?
**Answer:**
- Default: Data is stored in the AWS region where the cluster is deployed (e.g., us-east-1)
- Enterprise: Cross-region replication to a secondary region for disaster recovery
- EU Data: GDPR-compliant deployment in eu-west-1 with data never leaving EU
- Custom: On-premise deployment for organizations with strict data sovereignty requirements

---

## 6. Performance & Scaling

### Q6.1: What is the maximum throughput per pod?
**Answer:** Benchmarks on m6i.2xlarge (8 vCPU, 32GB RAM):

Scenario | RPS | P50 Latency | P99 Latency
Cache hit (L1) | 2,000 | 15ms | 25ms
Cache hit (L2) | 1,500 | 20ms | 35ms
Standard optimization | 500 | 320ms | 800ms
Aggressive optimization | 300 | 450ms | 1,200ms
Shadow testing enabled | 250 | 600ms | 1,500ms

Bottleneck: LLM provider API latency dominates. TokenOpt overhead is <20ms for cache hits and <50ms for optimizations.

### Q6.2: How does autoscaling work?
**Answer:** Three scaling mechanisms:
1. HPA (Horizontal Pod Autoscaler): Scales pods based on CPU (70%) and memory (80%). Range: 3-50 pods.
2. Cluster Autoscaler: Scales EKS nodes based on pending pod scheduling. Range: 3-20 nodes.
3. KEDA: Event-driven scaling for Kafka consumers based on lag metrics.

Scale-Up Time:
- Pod: 15-30 seconds (image pull + health check)
- Node: 2-3 minutes (EC2 instance provisioning)

Pre-Scaling: Scheduled scaling for known traffic patterns (e.g., scale to 10 pods at 9 AM).

### Q6.3: What is the cold start time?
**Answer:**

Component | Cold Start
Pod startup | 10-15 seconds
Model loading (sentence-transformers) | 5-8 seconds
Database connection pool | 2-3 seconds
Total cold start | ~20 seconds

Mitigation:
- Minimum 3 pods always running (no cold start for normal traffic)
- Pre-warming: New pods are added to the load balancer only after model loading completes
- Startup probes: Kubernetes waits for /health to return 200 before routing traffic

### Q6.4: How is memory managed?
**Answer:**

Per Pod:
- Base: 150MB
- Model: 500MB (loaded once, shared across workers)
- Cache: 200MB (configurable)
- Request buffers: ~100MB at 100 concurrent requests
- Total: ~1GB working set

OOM Prevention:
- Memory limits: 2GB (hard limit, pod killed if exceeded)
- Memory requests: 512MB (scheduling guarantee)
- Graceful degradation: If memory pressure >80%, cache size is reduced and non-critical background tasks are paused

### Q6.5: What happens during a traffic spike?
**Answer:**
1. 0-30 seconds: Existing pods handle spike. Rate limiting queues excess requests.
2. 30-60 seconds: HPA detects high CPU and scales pods. New pods enter startup.
3. 60-90 seconds: New pods ready. Load distributed. Queue drains.
4. If spike exceeds capacity: 429 Too Many Requests with Retry-After header

Circuit Breaker: If provider rate limits are hit, requests are queued with exponential backoff (max 30 seconds) before failing.

### Q6.6: How is database connection pooling configured?
**Answer:**

asyncpg Pool Settings:
- min_size: 5 connections per pod
- max_size: 20 connections per pod
- max_inactive_time: 300 seconds
- command_timeout: 60 seconds

Total Connections:
- 50 pods x 20 connections = 1,000 connections max
- RDS db.r6g.xlarge supports 2,000 connections -> 50% headroom
- PgBouncer (transaction pooling) available for enterprise tenants to reduce connection count

### Q6.7: What is the Redis cluster topology?
**Answer:**

Configuration:
- Mode: Redis Cluster (6 nodes: 3 masters, 3 replicas)
- Sharding: 16384 hash slots across 3 master nodes
- Replication: Async replication with replica-priority failover
- Persistence: AOF every second + RDB snapshot every hour

Client Configuration:
- Redis-py cluster client with retry logic
- Read from replicas for cache hits (load distribution)
- Write to master for cache updates
- Connection pooling: 10 connections per pod

### Q6.8: How is Kafka used?
**Answer:**

Topics:
- audit-events: All request/response data for async persistence
- optimization-metrics: Performance and savings metrics for analytics
- rollback-events: Quality failures for analysis
- provider-health: Provider status updates

Producers: TokenOpt proxy (fire-and-forget, batch size 100, linger 10ms)
Consumers: Background workers (3 replicas, auto-scaled via KEDA based on lag)

Purpose: Decouple request processing from audit logging to keep API latency low.

### Q6.9: What is the network bandwidth requirement?
**Answer:**

Per Request (typical):
- Request: 2KB (prompt + headers)
- Response: 5KB (completion + metadata)
- Total: 7KB

At 1000 RPS:
- Ingress: 2MB/s
- Egress: 5MB/s
- Total: 7MB/s = 56 Mbps

AWS ALB: Handles up to 100 Gbps per AZ. NLB for higher throughput.

### Q6.10: How is latency optimized?
**Answer:**

Technique | Latency Reduction
Connection pooling (DB, Redis, providers) | 5-10ms
HTTP/2 multiplexing | 3-5ms
Async I/O (no thread blocking) | 10-20ms
L1 cache (in-memory) | 15-20ms
L2 cache (Redis) | 10-15ms
Batch processing (Kafka) | 2-5ms
Total optimization | ~50ms

Provider Latency: TokenOpt cannot reduce LLM provider latency (~300ms for GPT-4), but it reduces token count which can reduce provider latency by 10-20%.


---

## 7. Operations & Monitoring

### Q7.1: What metrics are exposed?
**Answer:** Prometheus metrics at /metrics:

Request Metrics:
- tokenopt_requests_total (counter, labeled by status, provider, tenant)
- tokenopt_request_duration_seconds (histogram)
- tokenopt_request_size_bytes (histogram)
- tokenopt_response_size_bytes (histogram)

Optimization Metrics:
- tokenopt_savings_pct (gauge)
- tokenopt_fidelity_score (gauge)
- tokenopt_rollbacks_total (counter)
- tokenopt_cache_hits_total (counter)
- tokenopt_cache_misses_total (counter)

Business Metrics:
- tokenopt_cost_savings_total (counter, in USD)
- tokenopt_tokens_saved_total (counter)

Infrastructure Metrics:
- tokenopt_db_connections_active (gauge)
- tokenopt_redis_connections_active (gauge)
- tokenopt_provider_health (gauge, 0=unhealthy, 1=healthy)

### Q7.2: How is log aggregation configured?
**Answer:**

Stack: Fluent Bit -> CloudWatch Logs -> OpenSearch

Log Levels:
- ERROR: Failures, rollbacks, provider outages
- WARN: High latency, cache misses, rate limit approaches
- INFO: Request summaries, optimization decisions
- DEBUG: Detailed pipeline steps (disabled in production)

Structured Logging: JSON format with fields including timestamp, level, request_id, tenant_id, method, path, status, duration_ms, savings_pct, fidelity_score, provider.

### Q7.3: What alerts are configured by default?
**Answer:**

Alert | Condition | Severity | Notification
High Error Rate | Error rate >1% for 2 min | Critical | PagerDuty + Slack
Low Fidelity | Avg fidelity <0.99 for 5 min | Warning | Slack
High Rollback Rate | Rollback rate >2% for 5 min | Warning | Slack
High Latency | P95 latency >1s for 5 min | Warning | Slack
Provider Down | Provider unhealthy for 2 min | Critical | PagerDuty
Database Connection Pool Exhausted | Active connections >90% for 5 min | Critical | PagerDuty
Cache Hit Rate Low | Cache hit rate <50% for 10 min | Warning | Slack
Cost Spike | Hourly cost >200% of baseline | Warning | Slack
Disk Space | Node disk >85% | Warning | Slack
Memory Pressure | Node memory >90% | Critical | PagerDuty

### Q7.4: How is tracing implemented?
**Answer:** OpenTelemetry tracing:

Spans:
- tokenopt.request (root span)
  - auth.validate_jwt
  - rate_limit.check
  - optimize.prompt
    - optimize.filler_removal
    - optimize.semantic_compression
    - optimize.context_pruning
  - validate.fidelity
  - route.provider
  - provider.call
  - persist.audit

Export: Jaeger collector in-cluster, with sampling rate 1% in production (10% in staging).

### Q7.5: What is the on-call rotation?
**Answer:**

Rotation: 1-week primary, 1-week secondary (follow-the-sun across US and EU teams)

Escalation:
1. L1 (SRE): First responder, handles 80% of incidents
2. L2 (Platform Engineer): Escalation for code/deployment issues
3. L3 (Architecture Team): Escalation for design-level issues

Runbooks: All alerts link to specific runbook pages in the internal wiki.

### Q7.6: How are backups verified?
**Answer:**

Automated Verification:
- Weekly restore test from RDS snapshot to ephemeral instance
- Automated data integrity checks (row counts, checksums)
- Redis backup restoration test monthly

RTO/RPO Verification:
- Quarterly disaster recovery drill
- Simulated region failure, cross-region failover
- Documented recovery time vs. SLA targets

### Q7.7: What is the change management process?
**Answer:**

Change Types:
- Standard: Helm chart updates, config changes (approved by peer review)
- Normal: Application deployments (require QA sign-off)
- Emergency: Security patches, outage fixes (post-hoc review within 24 hours)

Process:
1. Change request in ServiceNow/Jira
2. Risk assessment (CAB for high-risk changes)
3. Staging deployment and testing
4. Production deployment during maintenance window
5. Post-deployment verification
6. Change closure with lessons learned

### Q7.8: How are security patches applied?
**Answer:**

Automated:
- Dependabot for Python dependencies (weekly PRs)
- Snyk for container image scanning (daily)
- AWS Systems Manager Patch Manager for OS patches (monthly)

Process:
1. Vulnerability detected (CVSS score)
2. Critical (CVSS >9): Patch within 24 hours
3. High (CVSS 7-9): Patch within 7 days
4. Medium/Low: Patch during next maintenance window

### Q7.9: What is the SLA?
**Answer:**

Tier | Uptime | Support | Response Time
Standard | 99.5% | Business hours | 4 hours
Enterprise | 99.9% | 24/7 | 1 hour
Premium | 99.99% | 24/7 | 15 minutes

Credits:
- <99.5%: 10% monthly credit
- <99.0%: 25% monthly credit
- <95.0%: 50% monthly credit + root cause analysis

### Q7.10: How is capacity planning done?
**Answer:**

Monthly Review:
1. Analyze growth trends (requests, tokens, tenants)
2. Project resource needs 3 months ahead
3. Adjust node pool sizes and RDS instance classes
4. Review cost optimization opportunities (Reserved Instances, Savings Plans)

Triggers for Immediate Scaling:
- Sustained CPU >70% for 1 hour
- Memory usage >80% for 30 minutes
- Database connections >80% of max
- Cache eviction rate >10%

---

## 8. Deployment & DevOps

### Q8.1: What is the CI/CD pipeline?
**Answer:** GitHub Actions workflow with four stages:
1. Test: Unit tests, integration tests, security scan (bandit, safety)
2. Build: Docker image build and push to ECR
3. Deploy Staging: Helm upgrade with smoke tests
4. Deploy Production: Canary deployment (10% -> 5 min analysis -> 100%)

### Q8.2: How are database migrations handled?
**Answer:**

Tool: Alembic (SQLAlchemy migrations)

Process:
1. Migration script created during development (alembic revision --autogenerate)
2. Reviewed in PR (schema changes require DBA approval)
3. Applied in staging automatically during deployment
4. Applied in production via init container or manual job
5. Backward-compatible migrations only (no destructive changes during deployment)

Rollback: Every migration has a corresponding downgrade script. Rollback is tested in staging.

### Q8.3: What is the canary deployment strategy?
**Answer:**

Phases:
1. Deploy: New version deployed to 10% of pods
2. Monitor: 5-minute observation of error rate, latency, fidelity
3. Analyze: Automated comparison against baseline
4. Promote: If healthy, rollout to 100%
5. Rollback: If error rate >0.1% or fidelity <0.99, automatic rollback

Implementation: Flagger (progressive delivery operator) with Prometheus metrics for analysis.

### Q8.4: How are secrets managed in CI/CD?
**Answer:**

GitHub Actions:
- Secrets stored in GitHub Secrets (encrypted at rest)
- AWS IAM OIDC provider for temporary credentials (no long-lived keys)
- Kubernetes secrets applied via sealed-secrets or external-secrets operator

Rotation:
- CI/CD secrets: Rotated quarterly
- AWS credentials: Temporary (1-hour TTL) via OIDC

### Q8.5: What is the rollback procedure?
**Answer:**

Application Rollback:
  helm rollback tokenopt -n tokenopt
  OR
  helm upgrade tokenopt ./helm-chart --set image.tag=v1.9.0 -n tokenopt --wait

Infrastructure Rollback:
  terraform state pull > backup.tfstate
  terraform apply -backup=backup.tfstate

Database Rollback:
  aws rds restore-db-instance-from-db-snapshot     --db-instance-identifier tokenopt-production     --db-snapshot-identifier tokenopt-stable-snapshot

### Q8.6: How are feature flags used?
**Answer:**

Tool: LaunchDarkly (enterprise) or Unleash (open-source)

Use Cases:
- Gradual rollout of new optimization techniques
- A/B testing of fidelity thresholds
- Emergency kill switches for problematic features
- Tenant-specific feature enablement

### Q8.7: What is the staging environment?
**Answer:**

Configuration:
- EKS cluster: tokenopt-staging
- Nodes: 2 x m6i.large (smaller than production)
- RDS: db.t3.medium (no Multi-AZ)
- Redis: cache.t3.micro (single node)
- Data: Synthetic data, no PII

Purpose: Pre-production testing, integration testing, performance baseline, security scanning.

### Q8.8: How are infrastructure changes tested?
**Answer:**

Terraform Testing:
1. terraform plan in PR for preview
2. terraform validate for syntax checking
3. Terratest (Go) for integration testing
4. Checkov/TFLint for security and best practices
5. Apply in staging first, then production

Kubernetes Testing:
1. helm lint for chart validation
2. helm template for rendered manifest review
3. kube-score for manifest best practices
4. kubeval for schema validation

### Q8.9: What is the disaster recovery plan?
**Answer:**

RTO/RPO by Scenario:

Scenario | RTO | RPO | Recovery Method
Pod failure | 30s | 0 | Kubernetes auto-restart
Node failure | 2 min | 0 | Pod rescheduling
AZ failure | 5 min | 0 | Multi-AZ failover
Region failure | 30 min | 5 min | Cross-region replica promotion
Data corruption | 1 hour | 24 hours | Snapshot restore

Cross-Region Setup:
- Primary: us-east-1
- Secondary: us-west-2
- RDS: Cross-region read replica
- Redis: Global Datastore (ElastiCache)
- EKS: Separate cluster with automated failover scripts

### Q8.10: How are costs monitored?
**Answer:**

AWS Cost Explorer:
- Daily cost alerts if >120% of budget
- Monthly cost allocation by service (EKS, RDS, ElastiCache, data transfer)

Internal Cost Tracking:
- Per-tenant cost attribution via resource tagging
- Cost per 1K requests by optimization level
- Provider cost comparison (OpenAI vs. Azure vs. Anthropic)

Optimization:
- Reserved Instances for baseline capacity
- Spot instances for non-critical background workers
- S3 Intelligent-Tiering for audit log archives


---

## 9. Data & Persistence

### Q9.1: What is the database schema?
**Answer:** Core tables include:

1. audit_logs (partitioned by day): request_id, tenant_id, timestamp, method, path, status_code, duration_ms, original_tokens, optimized_tokens, savings_pct, fidelity_score, was_rolled_back, provider, model, request_content (JSONB), response_content (JSONB), optimization_metadata (JSONB), ip_address

2. optimization_stats (materialized view refreshed hourly): tenant_id, hour, request_count, avg_savings, avg_fidelity, rollback_count, tokens_saved

3. tenant_configs: tenant_id, plan, optimization_level, fidelity_threshold, rate_limit_rpm, custom_templates (JSONB)

4. prompt_templates: id, tenant_id, name, pattern_regex, optimized_template, fidelity_score, usage_count, is_active

### Q9.2: How is data partitioned?
**Answer:**

Partitioning Strategy:
- audit_logs: Partitioned by day (RANGE partitioning on timestamp)
- Automatic partition creation via pg_cron (7 days ahead)
- Partition pruning ensures queries only scan relevant partitions
- Old partitions (90+ days) are detached and archived to S3

Benefits:
- Query performance: 10x faster for time-range queries
- Maintenance: Individual partitions can be vacuumed/analyzed independently
- Archiving: Drop old partitions instead of DELETE (instant, no bloat)

### Q9.3: What is the data retention policy?
**Answer:**

Data Type | Retention | Archive | Deletion
Audit logs | 90 days | S3 (Parquet) | After 2 years
Optimization stats | 1 year | S3 (CSV) | After 3 years
Rollback logs | 1 year | S3 | After 2 years
Tenant configs | Indefinite | -- | On tenant deletion
Prompt templates | Indefinite | -- | On template deletion

GDPR Compliance: Right to deletion within 30 days of request.

### Q9.4: How are materialized views refreshed?
**Answer:**

Schedule: Hourly via pg_cron
  SELECT cron.schedule('refresh-stats', '0 * * * *', 
    'REFRESH MATERIALIZED VIEW CONCURRENTLY optimization_stats');

Concurrent Refresh: Uses CONCURRENTLY flag to avoid locking reads during refresh.

Fallback: If refresh fails, the previous version remains available (stale but consistent).

### Q9.5: What is the Redis data model?
**Answer:**

Key Patterns:
- rate_limit:{tenant_id}:{minute_timestamp} -> integer (request count)
- cache:l1:{sha256(prompt)} -> optimization_result
- cache:l2:{simhash(prompt)} -> optimization_result
- circuit:{provider_name} -> {state: "closed", failures: 0, last_failure: null}
- session:{jwt_token_hash} -> {tenant_id, roles, exp}
- metrics:requests:{tenant_id}:{hour} -> counter
- metrics:savings:{tenant_id}:{hour} -> counter

TTL:
- Rate limits: 2 minutes
- L1 cache: 5 minutes
- L2 cache: 1 hour
- Sessions: JWT expiration
- Metrics: 24 hours

### Q9.6: How is Kafka data processed?
**Answer:**

Producer Configuration:
- Batch size: 100 messages
- Linger: 10ms
- Compression: LZ4
- Acknowledgments: 1 (fire-and-forget for audit logs)

Consumer Configuration:
- Group ID: tokenopt-audit-workers
- Auto-commit: False (manual commit after successful persistence)
- Max poll records: 500
- Processing: Async batch insert to PostgreSQL using COPY

Topic Retention:
- audit-events: 7 days
- optimization-metrics: 30 days
- rollback-events: 90 days
- provider-health: 1 day

### Q9.7: How are backups configured?
**Answer:**

PostgreSQL:
- Automated daily snapshots (RDS)
- Transaction logs archived to S3 every 5 minutes
- Point-in-Time Recovery (PITR) to any moment in the last 35 days
- Cross-region snapshot replication to us-west-2

Redis:
- Automated daily snapshots (ElastiCache)
- AOF persistence every second
- Manual snapshots before major changes

Kafka:
- Replication factor: 3 (across 3 brokers)
- Min ISR: 2
- Log retention: 7 days (configurable per topic)

### Q9.8: What is the data pipeline for analytics?
**Answer:**

TokenOpt Proxy -> Kafka -> Spark Streaming -> S3 (Raw)
                                      |
                                   Athena -> QuickSight Dashboards
                                      |
                                   Redshift -> BI Reports

Batch Processing:
- Hourly ETL from Kafka to S3 (Parquet format)
- Daily aggregation to Redshift
- Weekly ML model retraining from historical data

### Q9.9: How is PII handled?
**Answer:**

Collection:
- User ID (from JWT sub claim)
- IP address (anonymized: last octet zeroed)
- Request/response content (truncated to 10KB)

Protection:
- Encryption at rest (AES-256)
- Encryption in transit (TLS 1.3)
- Access logging for all PII access
- Annual privacy impact assessment

Retention:
- PII in audit logs: 90 days
- Anonymized analytics: Indefinite

### Q9.10: How is data migration handled between versions?
**Answer:**

Forward Compatibility:
- New columns are nullable with sensible defaults
- New tables are created in separate migrations
- API responses include only fields understood by the client

Backward Compatibility:
- Old columns are deprecated for 2 versions before removal
- Dual-write period for schema changes (write to old and new tables)
- Blue-green deployment for major schema changes

---

## 10. Business & Product

### Q10.1: What is the pricing model?
**Answer:**

Plan | Monthly Fee | Included Requests | Overage | Features
Developer | $0 | 10K | N/A | Basic optimization, community support
Standard | $499 | 1M | $0.50/K | Standard optimization, email support
Enterprise | $2,499 | 10M | $0.25/K | All features, SLA, dedicated support
Premium | Custom | Unlimited | -- | Custom models, on-premise, white-glove

Savings Guarantee: If token savings don't exceed platform cost within 30 days, full refund.

### Q10.2: How is ROI calculated?
**Answer:**

Formula:
  Monthly Savings = (Original Token Cost - Optimized Token Cost) - Platform Fee
  ROI = (Monthly Savings / Platform Fee) x 100%

Example:
- Original monthly spend: $10,000 (OpenAI)
- Optimized monthly spend: $6,000 (40% savings)
- Platform fee: $2,499
- Net savings: $10,000 - $6,000 - $2,499 = $1,501
- ROI: $1,501 / $2,499 = 60%

Dashboard: Real-time ROI calculator in Grafana dashboard.

### Q10.3: What is the onboarding process?
**Answer:**

Timeline: 1-2 days

Steps:
1. Account Setup: Tenant creation, JWT token generation
2. Integration: Update API base URL in your application (5 minutes)
3. Validation: Use /v1/tokenopt/validate to preview optimizations
4. Testing: Run test suite against staging environment
5. Go-Live: Switch production traffic
6. Optimization: Review dashboard, tune fidelity threshold if needed

Support: Dedicated onboarding engineer for Enterprise/Premium plans.

### Q10.4: What integrations are available?
**Answer:**

Native Integrations:
- OpenAI (Python, Node.js, REST)
- Azure OpenAI
- Anthropic Claude
- Google Gemini
- LangChain
- LlamaIndex
- Haystack

Monitoring Integrations:
- Datadog
- New Relic
- Dynatrace
- Splunk

CI/CD Integrations:
- GitHub Actions
- GitLab CI
- Jenkins
- CircleCI

### Q10.5: How are custom templates created?
**Answer:**

API:
  POST /v1/tokenopt/templates
  Authorization: Bearer $ADMIN_TOKEN
  Content-Type: application/json
  {
    "name": "legal-contract-summary",
    "pattern": "Summarize the following contract: (.+)",
    "optimized_template": "Contract summary: $1",
    "fidelity_threshold": 0.999
  }

Validation:
- Pattern must be valid regex
- Optimized template must preserve all capture groups
- Fidelity score >0.995 in 100 test cases

### Q10.6: What is the competitive advantage?
**Answer:**

Feature | TokenOpt | Competitor A | Competitor B
Token Savings | 30-60% | 15-25% | 20-30%
Fidelity Validation | Embedding + LLM Judge | Embedding only | None
Multi-Provider | OpenAI/Azure/Anthropic | OpenAI only | OpenAI/Azure
Auto-Rollback | Yes | No | No
On-Premise | Yes | No | No
Open Source | Core engine | No | No

### Q10.7: What is the roadmap?
**Answer:**

Q3 2026:
- Support for Google Gemini
- Custom model fine-tuning for enterprise
- Enhanced code optimization

Q4 2026:
- Multi-modal optimization (images, audio)
- Real-time collaborative editing optimization
- Advanced analytics dashboard

Q1 2027:
- Edge deployment (Cloudflare Workers)
- Automatic prompt engineering suggestions
- Integration with 20+ LLM frameworks

### Q10.8: How is customer support structured?
**Answer:**

Channel | Developer | Standard | Enterprise | Premium
Documentation | Yes | Yes | Yes | Yes
Community Forum | Yes | Yes | Yes | Yes
Email Support | No | Yes (48h) | Yes (24h) | Yes (4h)
Slack Channel | No | No | Yes | Yes
Dedicated CSM | No | No | No | Yes
On-Call Escalation | No | No | Yes (1h) | Yes (15min)
Custom Development | No | No | No | Yes

### Q10.9: What is the partner program?
**Answer:**

Technology Partners:
- Co-marketing opportunities
- Joint solution briefs
- Technical integration support
- Revenue sharing (15% of referred revenue)

Reseller Partners:
- White-label option
- Training and certification
- Deal registration protection
- Margin: 20-30%

### Q10.10: How are feature requests handled?
**Answer:**

Process:
1. Submit via GitHub Issues or customer portal
2. Product team reviews weekly
3. Impact assessment (user benefit x implementation effort)
4. Roadmap placement (next quarter or backlog)
5. Beta testing with interested customers
6. General availability

Enterprise customers: Direct input to quarterly roadmap planning.

---

## 11. Troubleshooting

### Q11.1: Why am I getting 401 Unauthorized?
**Answer:** Common causes:
1. Expired JWT: Check token expiration. Generate new token via admin panel.
2. Invalid Signature: Ensure JWT_SECRET matches between token generation and validation.
3. Missing Bearer: Header must be Authorization: Bearer <token>
4. Tenant Mismatch: Token's tenant_id doesn't match the request path.
5. Clock Skew: Server and client clocks must be within 5 minutes.

Debug: Decode token to verify claims using jwt decode command.

### Q11.2: Why are my requests not being optimized?
**Answer:** Checklist:
1. Optimization Level: Verify tenant config has optimization_level set to standard or aggressive
2. Prompt Length: Prompts <30 tokens are not optimized
3. Content Type: Legal/medical/creative prompts may bypass optimization
4. Cache Bypass: Cache-Control: no-cache disables caching but not optimization
5. Fidelity Pre-Check: If pre-check fails, original prompt is used
6. Disabled Techniques: Check tenant config for disabled techniques

Debug: Check optimization metadata in response for was_optimized: false and reason.

### Q11.3: Why is my fidelity score low?
**Answer:**
1. Aggressive Level: Switch from aggressive to standard
2. Domain Mismatch: Your domain may not be well-represented in training data
3. Complex Prompts: Multi-step reasoning prompts are harder to compress
4. Language: Non-English prompts may have lower fidelity
5. Template Gap: Your prompt pattern isn't in the template library

Fix: Use /v1/tokenopt/validate to preview optimization, adjust fidelity_threshold if needed.

### Q11.4: Why am I getting 429 Too Many Requests?
**Answer:**
1. TokenOpt Rate Limit: Check X-RateLimit-Remaining header
2. Provider Rate Limit: TokenOpt is being rate-limited by OpenAI/Azure
3. Burst Traffic: TokenOpt queues requests, but queue may be full
4. Tenant Quota: Monthly quota exceeded

Resolution: Wait and retry with exponential backoff, check rate limit headers for reset time, contact admin to increase quota, enable multiple providers for load distribution.

### Q11.5: Why is latency higher than expected?
**Answer:**

Symptom | Likely Cause | Fix
Consistently >500ms | Provider latency | Normal for GPT-4; use GPT-3.5 for faster responses
Spikes to >2s | Cold start / scaling | Pre-warm pods; increase min replicas
Gradual increase | Resource exhaustion | Scale up nodes or pods
Intermittent spikes | GC pauses | Increase memory limits
After deployment | New version regression | Rollback and investigate

### Q11.6: Why are my rollbacks increasing?
**Answer:**
1. New Prompt Patterns: Your application started sending new prompt types
2. Model Change: Provider model update changed output sensitivity
3. Threshold Too High: Fidelity threshold may be unrealistic for your use case
4. Template Conflict: Custom template is too aggressive
5. Bug: Regression in optimization engine

Investigation: Get rollback logs via API, analyze patterns for common techniques, prompt types, and fidelity scores.

### Q11.7: Why is my cache hit rate low?
**Answer:**
1. Unique Prompts: Each prompt is significantly different (low repetition)
2. Cache Size: Redis memory too small, evicting entries
3. TTL Too Short: Cache entries expire before reuse
4. SimHash Collisions: Similar prompts not matching due to threshold
5. Cache Disabled: Tenant config has caching disabled

Improvement: Increase Redis memory, increase TTL for stable prompt patterns, lower SimHash threshold, use prompt templates for common queries.

### Q11.8: Why am I getting 502 Bad Gateway?
**Answer:**
1. Provider Down: Check provider status page
2. TokenOpt Pod Crash: Check pod logs for OOM or panic
3. Network Issue: VPC routing or security group misconfiguration
4. Ingress Misconfiguration: TLS certificate expired or DNS issue

Debug: Check pod status, check logs, check provider health endpoint, test direct provider access.

### Q11.9: Why are my costs not decreasing?
**Answer:**
1. Short Prompts: Most prompts <30 tokens (not optimized)
2. Low Traffic: Savings don't offset platform fee
3. High Rollback Rate: Rollbacks use original tokens + optimization compute
4. Provider Switching: TokenOpt routed to more expensive provider
5. Shadow Testing: Enabled shadow testing doubles API calls

Analysis: Get detailed stats via API, check avg_savings_pct, rollback_rate, cache_hit_rate, and provider_distribution.

### Q11.10: How do I report a bug?
**Answer:**

GitHub Issues:
- Title: [BUG] Brief description
- Environment: production/staging/local
- Version: 2.0.0
- Steps to reproduce
- Expected behavior
- Actual behavior
- Logs (sanitized)
- Request ID (from response metadata)

Severity Levels:
- P0 (Critical): Complete outage, data loss, security breach -> Page on-call
- P1 (High): Major feature broken, significant performance degradation -> 4-hour response
- P2 (Medium): Minor feature issue, workaround exists -> 24-hour response
- P3 (Low): Cosmetic, documentation -> Next sprint

---

## 12. Development & Testing

### Q12.1: How do I set up a local development environment?
**Answer:**
1. Clone repository (`git clone https://github.com/rohit-naik36/TokenOpt.git`)
2. Create virtual environment (`python3 -m venv venv && source venv/bin/activate`)
3. Install dependencies (`cd tokenopt-proxy && pip install -r requirements.txt`)
4. Set required secrets (`export JWT_SECRET="production-tokenopt-secret-key-32chars-min"`)
5. Optional: Start backing services (`docker-compose up -d postgres redis kafka`) — TokenOpt automatically degrades gracefully with in-memory fallbacks if absent
6. Schema initialization is automatic on boot (`AuditDatabase.initialize()` provisions partitioned tables)
7. Start application (`uvicorn tokenopt_proxy_v2:app --reload --port 8000`)
8. Run tests (`pytest tests/ -v`)

### Q12.2: What is the testing strategy?
**Answer:**

Test Pyramid:
- Unit Tests (70%): 500+ tests for individual functions
- Integration Tests (20%): 100+ tests for component interactions
- E2E Tests (10%): 50+ tests for full request flows

Coverage:
- Minimum: 80% line coverage
- Target: 90% line coverage
- Critical paths: 100% coverage

Tools: pytest, pytest-asyncio, pytest-cov, factory_boy, moto (AWS mocking)

### Q12.3: How do I add a new optimization technique?
**Answer:**
1. Create technique class inheriting from OptimizationTechnique
2. Implement optimize() and estimate_savings() methods
3. Register in config (TECHNIQUES list)
4. Requirements: Fidelity score >0.995 on benchmark, latency <10ms, rollback rate <1%

### Q12.4: How do I contribute to the project?
**Answer:**
1. Fork repository
2. Create feature branch
3. Implement changes with tests
4. Run linting (black, isort, flake8, mypy)
5. Submit PR with description and test results
6. Code review by 2 maintainers
7. Merge after CI passes

CLA: All contributors must sign the Contributor License Agreement.

### Q12.5: What is the code style?
**Answer:**

Formatting:
- Black (line length: 100)
- isort (import sorting)
- flake8 (linting)
- mypy (type checking, strict mode)

Pre-commit Hooks:
- black
- isort
- flake8

### Q12.6: How are dependencies managed?
**Answer:**

Production: requirements.txt (pinned versions)
Development: requirements-dev.txt (includes testing tools)
Security: Dependabot weekly PRs, Snyk daily scans

Update Process:
1. Dependabot creates PR
2. CI runs tests
3. Security review for major version bumps
4. Merge if tests pass

### Q12.7: What is the release process?
**Answer:**

Versioning: Semantic Versioning (MAJOR.MINOR.PATCH)

Release Checklist:
1. Update CHANGELOG.md
2. Bump version in pyproject.toml and helm-chart/Chart.yaml
3. Create release branch
4. Run full test suite
5. Build and tag Docker image
6. Deploy to staging
7. Run smoke tests
8. Create GitHub release with notes
9. Deploy to production (canary)
10. Monitor for 24 hours
11. Announce in Slack #releases

### Q12.8: How is documentation maintained?
**Answer:**

Structure:
- docs/architecture/: System design docs
- docs/api/: OpenAPI specs and guides
- docs/runbooks/: Operational procedures
- docs/adr/: Architecture Decision Records

Tools:
- MkDocs for static site generation
- OpenAPI Generator for API docs
- Mermaid for diagrams
- GitHub Pages for hosting

### Q12.9: What is the performance benchmarking process?
**Answer:**

Benchmarks:
- benchmarks/latency.py: P50/P95/P99 latency
- benchmarks/throughput.py: Max RPS per pod
- benchmarks/savings.py: Token savings accuracy
- benchmarks/fidelity.py: Fidelity score distribution

Environment:
- Dedicated EKS cluster (no other workloads)
- Fixed node type (m6i.2xlarge)
- Warmed-up pods (no cold start)
- Synthetic load (k6)

Reporting:
- Results committed to benchmarks/results/
- Regression alerts if P95 latency increases >10%

### Q12.10: How are security vulnerabilities handled?
**Answer:**

Disclosure:
- Email: security@tokenopt.yourcompany.com
- GPG key available on security page
- Response within 24 hours

Process:
1. Acknowledge receipt
2. Assess severity (CVSS)
3. Develop fix
4. Test fix
5. Coordinate disclosure (if applicable)
6. Release patch
7. Public disclosure (if applicable)

Bug Bounty: HackerOne program for external researchers.

---

Document Owner: Platform Engineering & Developer Relations
Review Cycle: Monthly
Last Updated: July 2026
Feedback: Submit questions via GitHub Issues or #tokenopt-questions Slack channel
