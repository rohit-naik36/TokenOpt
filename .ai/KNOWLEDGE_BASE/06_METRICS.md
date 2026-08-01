# 06 — Metrics

*Part of the [Architecture Knowledge Base](README.md).*

## Ownership

Metrics are produced in three strictly separated layers:

| Layer | Owns | Writes |
|-------|------|--------|
| Pipeline stages | per-stage outcome facts | `ctx.metrics` string keys (`routing_rule`, `compression_applied`, `cache_hit`, `rag_optimized_chunks`, `final_token_count`, `{stage}_error`, `{stage}_latency_ms`, ...) |
| Client (`_record_metrics`) | the **single mapper** stage-vocabulary → public vocabulary | `RequestMetrics` objects |
| `MetricsCollector` | aggregation, callbacks, thread safety | counters + summary |

Rule: stages never construct `RequestMetrics`; the client never writes
directly to the collector's internals; the collector never knows about
pipeline keys. This one-directional ownership is a contract
([07 — Architectural Contracts](07_ARCHITECTURAL_CONTRACTS.md)).

## Propagation flow

```
stage → ctx.metrics (string keys)
  → BaseOptimizedClient._record_metrics   (single mapping point)
  → RequestMetrics (public dataclass)
      → MetricsCollector.record  (lock, counters, guarded callback)
      → StructuredLogger.log_request (one JSON line per request)
  → caller: get_metrics_summary() / get_recent(n) / callback
```

`_record_metrics` derives everything from `ctx` + the provider response:

- `optimized_tokens` = `final_token_count` (fallback: original)
- `tokens_saved` = original − optimized (may be negative)
- `reduction_percentage` = saved / original × 100
- `routing_applied` = any `routing_rule`/`routed_model` marker
- `estimated_cost` = `estimate_cost(model, original_tokens, output_tokens)`
- `compression_effective` = tokens_saved > 0
- latencies: total (`latency_ms`), pipeline middleware
  (`pipeline_latency_ms`), inference (`model_latency_ms` = total − pipeline)

## routing_reason

`RequestMetrics.routing_reason` is populated **only** from `ctx.metrics`
(`Decision 20`) — the client mirrors the router, so the report can never
disagree with the decision:

1. Matched rule → the rule name (`routing_rule`), e.g. `math_tasks`.
2. Else complexity routing → `complexity-based (low|medium|high)`.
3. Else preserved no-match → `preserved (no rule matched)`.
4. Else empty.

## routing_precedence

Every routing decision records one of five values (`Decision 24`):

| Value | Meaning |
|-------|---------|
| `explicit` | Caller passed `model=`; never overridden (precedence 1) |
| `rule` | A matching rule won by priority (precedence 2) |
| `preserve` | Custom rules exist, none matched — caller's model kept (precedence 3) |
| `complexity` | No custom rules — built-in complexity heuristic (precedence 4) |
| `provider_default` | No query to route on; resolved model stands (precedence 5) |

## Latency

Three numbers per request, always `total = pipeline + model`:

- `latency_ms` — end-to-end, from `chat_completion` entry to return.
- `pipeline_latency_ms` — `OptimizationPipeline.run` duration
  (middleware overhead; includes per-stage timing recorded as
  `{stage}_latency_ms` in `ctx.metrics`).
- `model_latency_ms` — provider inference time
  (`max(0, total − pipeline)`).

## Cost

`estimate_cost(model, input_tokens, output_tokens)` computes
USD from `MODEL_COSTS` (`observability/metrics.py`) — per-1M-token
input/output prices for gpt-4o/4o-mini/4-turbo/3.5-turbo, o1-preview/
o1-mini, claude-3-5-sonnet/haiku, claude-3-opus. Unknown models estimate
$0 (degraded, honest). The table is code-embedded today; a cost-source
abstraction is tracked (ADB-05).

## Observability philosophy

- **Built-in, zero extra dependencies**: metrics and JSON logging are part
  of the SDK (`Decision 5`).
- **Never breaks the request**: the user callback is guarded; collector
  exceptions are swallowed (`Decision 21`).
- **Additive-only vocabulary**: new metric fields are added, never
  redefined, so consumers and tests stay valid (`Decision 19` precedent;
  the `compression_attempted`/`compression_effective`/`tokens_saved`/
  `reduction_percentage`/`model_latency_ms` additions follow this rule).
- **Offline by default**: aggregation is in-memory (`get_summary`,
  `get_recent`); external sinks are the user's job via `metrics_callback`
  (Prometheus/StatsD adapters are future opportunities).
- **Aggregation**: `MetricsCollector` keeps counters (total_requests,
  cache_hits, compression_count, summarization_count, routing_count,
  errors) and computes cache-hit-rate, avg token reduction (+%),
  avg latency, total estimated cost, error rate, and optimization usage.
