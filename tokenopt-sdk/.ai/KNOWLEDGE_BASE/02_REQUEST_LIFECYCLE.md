# 02 — Request Lifecycle

*Part of the [Architecture Knowledge Base](README.md).*

## The complete flow

One optimized request travels through exactly one path:

```
Caller
  │  client.chat.completions.create(messages, model?)   (drop-in surface)
  ▼
Compat shim (_CompatShim) ──► client.chat_completion(messages, model, model_explicit?, **kwargs)
  │
  ▼
BaseOptimizedClient.chat_completion
  │  1. resolve explicitness + default model
  │  2. pipeline.run(messages, model, model_explicit, **kwargs)
  ▼
OptimizationPipeline.run
  │  create OptimizationContext (snapshot originals)
  │  router → compressor → summarizer → cache → rag → fewshot
  │  (each stage: guarded — fail-open; timed; writes ctx.metrics)
  │  final token metrics computed
  ▼
cache hit?  ── yes ──► _record_metrics(cache_hit=True) ──► return cached_response
  │ no
  ▼
_call_api(optimized messages, routed model)      ← provider seam #2
  │  (errors: record error metrics, re-raise to caller)
  ▼
response
  │
  ├─► CacheStage.store_response(ctx, response)   (async-style store after call)
  ▼
_record_metrics(...)  ──► MetricsCollector.record(RequestMetrics)
                          └─► callback (guarded) + StructuredLogger.log_request (JSON)
  ▼
return response  ──► Caller
```

## Every transition explained

### 1. Caller → compat shim

The drop-in surface (`client.chat.completions.create(...)` for OpenAI and
local, `client.messages.create(...)` for Anthropic) is implemented by one
shared `_CompatShim` (`tokenopt/clients/_compat.py`): `create()` forwards
straight to `chat_completion()`, so **every** entry point — drop-in surface
or direct method — funnels through the same optimized path. There is exactly
one implementation of this forwarding logic for all providers (M13 R4).

### 2. Shim → chat_completion

`BaseOptimizedClient.chat_completion` (`tokenopt/clients/base.py`):

- Derives `model_explicit` (whether the caller passed `model=`) — the
  routing contract's first input (`Decision 24`).
- Resolves the model default (`config.default_model`).

### 3. chat_completion → pipeline

`OptimizationPipeline.run(messages, model, model_explicit, **kwargs)`
(`tokenopt/pipeline/base.py`):

- Constructs a fresh `OptimizationContext` per request; `**kwargs` land in
  `ctx.metadata` (forwarded to the provider call later).
- Runs each enabled stage in order; a stage exception is swallowed and
  recorded (`{stage}_error`) — fail-open.
- Computes final token metrics (`final_token_count`, `token_reduction*`).

### 4. Pipeline → provider

`self._call_api(ctx.messages, ctx.model, **kwargs)` — the provider seam.
Only two outcomes:

- **Success**: response normalized to the shared shape where needed
  (see [04 — Provider Layer](04_PROVIDER_LAYER.md)).
- **Provider error**: metrics recorded with the error message, then the
  exception re-raised — the caller sees genuine API failures, never
  optimization failures.

### 5. Provider → cache

After a successful call the client hands `(ctx, response)` to
`CacheStage.store_response`, which stores under the key/embedding computed
earlier in the pipeline. Caching is therefore **write-through after the
call, look-up during the pipeline** (see [03 — Pipeline](03_PIPELINE.md)).

### 6. Response → metrics

`_record_metrics` is the **single mapper** from the pipeline's
`ctx.metrics` vocabulary to the public `RequestMetrics` object (see
[06 — Metrics](06_METRICS.md)). `MetricsCollector.record` aggregates under a
lock, invokes the user callback (guarded), and the `StructuredLogger`
emits one JSON line per request.

### 7. Metrics → caller

The original provider response object is returned to the caller untouched —
the drop-in contract means the caller's code sees exactly what the provider
returned (a cache hit returns the stored response object instead).

## Lifecycle branches

| Branch | Where decided | Effect |
|--------|---------------|--------|
| Cache hit | `CacheStage.process` sets `ctx.metadata["cache_hit"]` | Pipeline still completes; client returns `cached_response`; `cache_hit=True` in metrics; **no API call** |
| Stage failure | pipeline `run` per-stage guard | Stage skipped; `{stage}_error` metric; request continues unoptimized for that stage |
| Provider failure | `chat_completion` around `_call_api` | Error metrics recorded; exception propagates to caller |
| Metrics-callback failure | `MetricsCollector.record` | Swallowed — observability never breaks the request |

## Mermaid view

```mermaid
sequenceDiagram
    participant C as Caller
    participant S as _CompatShim
    participant B as BaseOptimizedClient
    participant P as Pipeline (6 stages)
    participant X as Provider API
    participant M as MetricsCollector

    C->>S: create(messages, model?)
    S->>B: chat_completion(messages, model, model_explicit)
    B->>P: run(ctx)
    Note over P: fail-open per stage; cache lookup inside
    alt cache hit
        P-->>B: cached_response
    else cache miss
        P->>B: optimized ctx
        B->>X: _call_api(messages, routed model)
        X-->>B: response
        B->>P: store_response(ctx, response)
    end
    B->>M: record(RequestMetrics) + log_request
    B-->>S: response
    S-->>C: response (drop-in shape)
```

## Key properties

- **One entry point per client** (`chat_completion`) — auditing and
  instrumentation are complete by construction.
- **Fail-open happens inside the pipeline**, never at the client boundary.
- **The response object is opaque to the framework** — only
  `_extract_response_content` and `_extract_usage` read it, and only for
  metrics.
