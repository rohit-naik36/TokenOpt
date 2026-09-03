# TokenOpt Enterprise — API Specification
## OpenAPI 3.0.3

**Version:** 2.0.0  
**Base URL:** `https://api.tokenopt.yourcompany.com`  
**Authentication:** Bearer JWT

---

## Authentication

All API requests require a JWT token in the Authorization header:

```
Authorization: Bearer <jwt_token>
```

Token generation:
```bash
jwt encode --secret "$JWT_SECRET" --exp="+90d" '{
  "tenant_id": "your-tenant",
  "sub": "user@company.com",
  "roles": ["user"],
  "plan": "enterprise"
}'
```

---

## Endpoints

### 1. Health Check

```
GET /health
```

**Description:** Check platform health and component status.

**Authentication:** None

**Response:**
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "timestamp": "2026-07-24T00:00:00Z",
  "services": {
    "database": "connected",
    "redis": "connected",
    "kafka": "connected",
    "providers": {
      "openai": "healthy",
      "azure": "healthy",
      "anthropic": "healthy"
    }
  }
}
```

**Status Codes:**
- `200 OK`: All services healthy
- `503 Service Unavailable`: One or more services unhealthy

---

### 2. List Models (Planned)

```
GET /v1/models
```

**Description:** List available LLM models from configured providers. *(Planned feature — in v2.0, configure models via environment and provider router).*

**Authentication:** JWT required

**Response:**
```json
{
  "object": "list",
  "data": [
    {
      "id": "gpt-4",
      "object": "model",
      "created": 1687882411,
      "owned_by": "openai"
    },
    {
      "id": "gpt-4-turbo",
      "object": "model",
      "created": 1699053533,
      "owned_by": "openai"
    },
    {
      "id": "claude-3-opus",
      "object": "model",
      "created": 1709251200,
      "owned_by": "anthropic"
    }
  ]
}
```

---

### 3. Chat Completions (Optimized)

```
POST /v1/chat/completions
```

**Description:** Create a chat completion with automatic token optimization, semantic compression, fidelity validation, and provider routing.

**Authentication:** JWT required

**Headers:**
- `Authorization: Bearer <token>` (required)
- `Content-Type: application/json` (required)

**Request Body:**
```json
{
  "model": "gpt-4",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful assistant."
    },
    {
      "role": "user",
      "content": "Explain quantum computing in simple terms."
    }
  ],
  "temperature": 0.7,
  "max_tokens": 500,
  "stream": false,
  "optimization_level": "standard",
  "skip_optimization": false,
  "fidelity_threshold": 0.995,
  "preferred_provider": "openai"
}
```

**TokenOpt Request Extensions (JSON Body):**
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `optimization_level` | string | `"standard"` | Optimization aggressiveness: `"standard"`, `"aggressive"`, or `"conservative"` |
| `skip_optimization` | boolean | `false` | When `true`, bypasses optimization pipeline and passes prompt directly |
| `fidelity_threshold` | float | config default (0.995) | Custom minimum fidelity threshold (0.0 to 1.0) for this request |
| `preferred_provider` | string | `null` | Force routing to a specific provider: `"openai"`, `"azure"`, `"anthropic"`, `"gemini"` |

**Response:**
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1721782800,
  "model": "gpt-4",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Quantum computing is a type of computing that uses quantum mechanics..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 24,
    "completion_tokens": 150,
    "total_tokens": 174
  },
  "tokenopt": {
    "version": "2.0.0",
    "request_id": "uuid-v4-string",
    "savings_pct": 42.5,
    "token_savings": 18,
    "original_tokens": 42,
    "optimized_tokens": 24,
    "fidelity_score": 0.9978,
    "fidelity_passed": true,
    "techniques": ["filler_removal:4", "semantic_compression"],
    "cache_hit": false,
    "was_optimized": true,
    "was_rolled_back": false,
    "optimization_latency_ms": 12.4,
    "provider_latency_ms": 234.1,
    "total_latency_ms": 246.5,
    "estimated_cost_original": 0.00126,
    "estimated_cost_optimized": 0.00072,
    "cost_savings": 0.00054,
    "provider": "openai"
  }
}
```

**Status Codes:**
- `200 OK`: Successful completion
- `400 Bad Request`: Invalid request body
- `401 Unauthorized`: Invalid or expired JWT
- `429 Too Many Requests`: Rate limit exceeded
- `502 Bad Gateway`: Provider error
- `503 Service Unavailable`: Platform unhealthy

**Rate Limit Headers:**
- `X-RateLimit-Limit: 1000`
- `X-RateLimit-Remaining: 999`
- `X-RateLimit-Reset: 1721782860`

---

### 4. Streaming Chat Completions

```
POST /v1/chat/completions
```

**Description:** Create a streaming chat completion with Server-Sent Events.

**Authentication:** JWT required

**Request Body:**
```json
{
  "model": "gpt-4",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "stream": true
}
```

**Response:** Server-Sent Events (SSE)

```
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1721782800,"model":"gpt-4","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1721782800,"model":"gpt-4","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1721782800,"model":"gpt-4","choices":[{"index":0,"delta":{"content":"!"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1721782800,"model":"gpt-4","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: {"tokenopt":{"version":"2.0.0","savings_pct":35.2,"fidelity_score":0.998,"provider":"openai"}}

data: [DONE]
```

---

#### 5. Create Embeddings (Planned)

```
POST /v1/embeddings
```

**Description:** Create embeddings with optimization (input text compression before embedding generation). *(Planned feature — in v2.0, embeddings are handled internally for fidelity validation).*

**Authentication:** JWT required

**Request Body:**
```json
{
  "model": "text-embedding-ada-002",
  "input": "The food was delicious and the waiter was very friendly."
}
```

**Response:**
```json
{
  "object": "list",
  "data": [
    {
      "object": "embedding",
      "embedding": [0.0023, -0.0091],
      "index": 0
    }
  ],
  "model": "text-embedding-ada-002",
  "usage": {
    "prompt_tokens": 11,
    "total_tokens": 11
  },
  "tokenopt": {
    "savings_pct": 15.3,
    "original_tokens": 13,
    "optimized_tokens": 11,
    "fidelity_score": 0.9991,
    "provider": "openai"
  }
}
```

---

### 6. Platform Statistics

```
GET /v1/tokenopt/stats?hours=24
```

**Description:** Retrieve platform performance, cache hit rate, provider latency, and cost savings statistics.

**Authentication:** JWT required

**Query Parameters:**
- `hours` (integer, optional, default: `24`): Time window in hours.

**Response:**
```json
{
  "tenant_id": "engineering",
  "period_hours": 24,
  "database": {
    "total_requests": 145230,
    "total_original_tokens": 58092000,
    "total_optimized_tokens": 34855200,
    "total_savings_pct": 40.0,
    "total_cost_savings": 697.10,
    "average_fidelity": 0.9976,
    "rollback_count": 218,
    "rollback_rate_pct": 0.15
  },
  "cache": {
    "hits": 65353,
    "misses": 79877,
    "hit_rate_pct": 45.0,
    "evictions": 1200
  },
  "providers": {
    "openai": {"status": "healthy", "error_rate": 0.001, "p95_latency_ms": 320},
    "azure": {"status": "healthy", "error_rate": 0.002, "p95_latency_ms": 280},
    "anthropic": {"status": "healthy", "error_rate": 0.000, "p95_latency_ms": 450}
  },
  "fidelity": {
    "total_validations": 145230,
    "passed": 145012,
    "failed": 218,
    "pass_rate_pct": 99.85,
    "avg_score": 0.9976
  },
  "platform": {
    "version": "2.0.0",
    "max_concurrent": 100,
    "fidelity_threshold": 0.995,
    "llm_judge_enabled": true
  }
}
```

---

### 7. Rollback Logs

```
GET /v1/tokenopt/rollbacks?limit=100
```

**Description:** Retrieve recent optimization rollback events for quality auditing.

**Authentication:** JWT required

**Query Parameters:**
- `limit` (integer, optional, default: `100`): Maximum entries to return.

**Response:**
```json
{
  "tenant_id": "engineering",
  "rollbacks": [
    {
      "request_id": "uuid-1234",
      "timestamp": "2026-07-24T14:23:05Z",
      "model": "gpt-4",
      "fidelity_score": 0.9912,
      "threshold": 0.995,
      "rollback_reason": "Fidelity 0.991 below threshold 0.995",
      "original_tokens": 450,
      "optimized_tokens": 450
    }
  ],
  "count": 1
}
```

---

### 8. Preview Optimization

```
POST /v1/tokenopt/validate?prompt=...
```

**Description:** Preview how a prompt would be optimized without making an LLM API call.

**Authentication:** JWT required

**Query Parameters:**
- `prompt` (string, required): The prompt text to optimize and preview.

**Response:**
```json
{
  "original": "Please provide a detailed explanation of quantum computing principles and their applications in modern cryptography.",
  "optimized": "Explain quantum computing principles and applications in cryptography.",
  "original_tokens": 19,
  "optimized_tokens": 11,
  "savings_pct": 42.1,
  "fidelity_score": 0.9985,
  "fidelity_passed": true,
  "techniques": ["filler_removal:3", "semantic_compression"],
  "estimated_cost_savings": "$0.000240"
}
```

---

### 9. Submit Feedback (Roadmap)

```
POST /v1/tokenopt/feedback
```

**Description:** Submit feedback on optimization quality. *(Enterprise roadmap feature)*.

**Authentication:** JWT required

**Request Body:**
```json
{
  "request_id": "uuid-from-response",
  "rating": "poor",
  "reason": "meaning_changed",
  "comment": "The optimized prompt changed the expected output format."
}
```

---

### 10. Tenant Configuration (Admin Roadmap)

```
GET /v1/admin/tenant/config
PATCH /v1/admin/tenant/config
```

**Description:** View and update tenant optimization settings. *(Enterprise roadmap feature)*.

**Authentication:** JWT required with `admin` role

**GET Response:**
```json
{
  "tenant_id": "engineering",
  "plan": "enterprise",
  "optimization_level": "standard",
  "fidelity_threshold": 0.995,
  "rate_limit_rpm": 10000,
  "enable_shadow_testing": true,
  "enable_auto_rollback": true,
  "custom_templates": [],
  "disabled_techniques": [],
  "created_at": "2024-01-15T00:00:00Z",
  "updated_at": "2026-07-24T00:00:00Z"
}
```

**PATCH Request Body:**
```json
{
  "optimization_level": "aggressive",
  "fidelity_threshold": 0.99
}
```

---

## Error Responses

All errors follow this format:

```json
{
  "error": {
    "code": "invalid_request",
    "message": "The request body is malformed.",
    "type": "invalid_request_error",
    "param": "messages",
    "request_id": "uuid-for-debugging"
  }
}
```

**Error Codes:**

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `invalid_request` | 400 | Malformed request |
| `unauthorized` | 401 | Invalid or missing JWT |
| `forbidden` | 403 | Insufficient permissions |
| `not_found` | 404 | Resource not found |
| `rate_limit_exceeded` | 429 | Too many requests |
| `provider_error` | 502 | LLM provider error |
| `service_unavailable` | 503 | Platform unhealthy |
| `internal_error` | 500 | Unexpected server error |

---

## Rate Limits

| Plan | Requests/Minute | Requests/Hour | Requests/Day |
|------|-------------------|---------------|--------------|
| Developer | 60 | 1,000 | 10,000 |
| Standard | 1,000 | 50,000 | 1,000,000 |
| Enterprise | 10,000 | 500,000 | 10,000,000 |
| Premium | Custom | Custom | Custom |

**Burst Limit:** 2x the per-minute limit for 10 seconds.

---

**Document Owner:** API Engineering Team  
**Review Cycle:** Monthly  
**Last Updated:** July 2026
