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

### 2. List Models

```
GET /v1/models
```

**Description:** List available LLM models.

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

**Description:** Create a chat completion with automatic token optimization.

**Authentication:** JWT required

**Headers:**
- `Authorization: Bearer <token>` (required)
- `Content-Type: application/json` (required)
- `X-TokenOpt-Optimization: {none|light|standard|aggressive}` (optional, default: tenant config)
- `X-TokenOpt-Fidelity-Threshold: 0.995` (optional)

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
  "stream": false
}
```

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

### 5. Create Embeddings

```
POST /v1/embeddings
```

**Description:** Create embeddings with optimization (input text compression before embedding generation).

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
      "embedding": [0.0023, -0.0091, ...],
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
GET /v1/tokenopt/stats
```

**Description:** Get platform usage and optimization statistics.

**Authentication:** JWT required (admin role for all tenants, user role for own tenant)

**Query Parameters:**
- `hours` (integer, optional): Time window in hours (default: 24, max: 720)
- `tenant_id` (string, optional): Filter by tenant (admin only)

**Response:**
```json
{
  "period_hours": 24,
  "total_requests": 2450000,
  "total_original_tokens": 890000000,
  "total_optimized_tokens": 520000000,
  "avg_savings_pct": 41.5,
  "avg_fidelity": 0.9975,
  "rollback_rate": 0.8,
  "cache_hit_rate": 62.3,
  "total_cost_savings": 12500.50,
  "provider_distribution": {
    "openai": 65.2,
    "azure": 25.1,
    "anthropic": 9.7
  },
  "optimization_level_distribution": {
    "none": 5.0,
    "light": 15.0,
    "standard": 65.0,
    "aggressive": 15.0
  }
}
```

---

### 7. Rollback Logs

```
GET /v1/tokenopt/rollbacks
```

**Description:** Get recent rollback events for quality analysis.

**Authentication:** JWT required (admin role)

**Query Parameters:**
- `hours` (integer, optional): Time window (default: 24)
- `limit` (integer, optional): Max results (default: 100, max: 1000)
- `tenant_id` (string, optional): Filter by tenant

**Response:**
```json
{
  "total": 45,
  "rollbacks": [
    {
      "request_id": "uuid-1",
      "timestamp": "2026-07-24T00:00:00Z",
      "tenant_id": "engineering",
      "fidelity_score": 0.9823,
      "threshold": 0.995,
      "technique": "semantic_compression",
      "original_prompt": "Please provide a detailed explanation...",
      "optimized_prompt": "Explain...",
      "reason": "fidelity_below_threshold"
    }
  ]
}
```

---

### 8. Preview Optimization

```
POST /v1/tokenopt/validate
```

**Description:** Preview how a prompt would be optimized without making an LLM API call.

**Authentication:** JWT required

**Request Body:**
```json
{
  "model": "gpt-4",
  "messages": [
    {"role": "user", "content": "Please provide a detailed explanation of quantum computing principles and their applications in modern cryptography."}
  ],
  "optimization_level": "standard"
}
```

**Response:**
```json
{
  "original_prompt": "Please provide a detailed explanation of quantum computing principles and their applications in modern cryptography.",
  "optimized_prompt": "Explain quantum computing principles and applications in cryptography.",
  "original_tokens": 19,
  "optimized_tokens": 11,
  "savings_pct": 42.1,
  "fidelity_score": 0.9985,
  "fidelity_passed": true,
  "techniques": ["filler_removal:3", "semantic_compression"],
  "estimated_cost_original": 0.00057,
  "estimated_cost_optimized": 0.00033,
  "cost_savings": 0.00024
}
```

---

### 9. Submit Feedback

```
POST /v1/tokenopt/feedback
```

**Description:** Submit feedback on optimization quality.

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

**Response:**
```json
{
  "status": "received",
  "request_id": "uuid-from-response",
  "ticket_id": "feedback-12345"
}
```

---

### 10. Tenant Configuration (Admin)

```
GET /v1/admin/tenant/config
PATCH /v1/admin/tenant/config
```

**Description:** View and update tenant optimization settings.

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
