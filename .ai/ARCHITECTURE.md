# Architecture

_Last updated: 2026-08-01_

## Overview

TokenOpt is a drop-in SDK: user code keeps the same import/API surface
(`OpenAI`, `Anthropic`) while requests flow through an optimization pipeline.

```
User code
   │
   ▼
Client wrapper (OpenAI / Anthropic / LocalClient)
   │  chat_completion(messages, model)
   ▼
OptimizationPipeline  ──►  OptimizationContext(messages, model, metrics)
   │
   ├─ 1. RouterStage          (select cheapest/smartest model)      [cloud clients]
   ├─ 2. CompressorStage      (heuristic or LLMLingua compression)
   ├─ 3. ContextSummarizerStage (summarize history above threshold)
   ├─ 4. CacheStage           (semantic cache: exact + similarity, LRU, optional Redis)
   ├─ 5. RAGOptimizerStage    (trim/rank "context:"/"retrieved:" chunks)
   └─ 6. FewShotSelectorStage (select examples by similarity/diversity)
   │
   ▼
Underlying API call (openai / anthropic / ollama / OpenAI-compatible)
   │
   ▼
Response  ──►  CacheStage.store_response()  ──►  MetricsCollector.record()
```

## Module layout

```
tokenopt/
├── __init__.py          # public API surface
├── config.py            # TokenOptConfig, RoutingRule, get_default_config()
├── factory.py           # create_client / create_client_from_model / detect_provider
├── clients/
│   ├── base.py          # BaseOptimizedClient (pipeline + metrics wiring)
│   ├── openai_client.py # OpenAI drop-in
│   ├── anthropic_client.py
│   └── local_client.py  # Ollama (native) / vLLM / llama.cpp (OpenAI-compatible)
├── pipeline/            # OptimizationContext, PipelineStage, OptimizationPipeline + 6 stages
├── observability/       # MetricsCollector, RequestMetrics, estimate_cost, StructuredLogger
└── utils/               # token_counter (tiktoken), embeddings (ST + fallback)
```

## Key flows

- **Cache hit** — CacheStage short-circuits; metrics record `cache_hit=True`,
  no API call.
- **Routing** — Router runs first and mutates `ctx.model`; compression targets
  based on that model's tokenizer. `LocalClient` drops the router unless custom
  rules target local models (Decision 8). Routing precedence (Decision 24):
  1. **Explicit caller model** — a `model=` passed to the client is never
     overridden (`ctx.model_explicit`).
  2. **Matching rule** — rules (custom and built-in) in priority order;
     first match wins.
  3. **Custom rules exist but none match** — the caller's requested model is
     preserved (never rewritten; fail-open).
  4. **No custom routing configuration** — built-in complexity routing
     (keyword + token-count heuristic).
  5. **Provider default** — nothing routes; the resolved model stands.
  Built-in rules (`RoutingRule.builtin=True`) ship with
  `get_default_config()`; only user-supplied rules count as "custom" for
  precedence 3 vs 4, so default-config behavior is unchanged. Every
  decision is recorded (`routing_precedence`, `routing_rule`,
  `routing_complexity`) and surfaced via `RequestMetrics.routing_reason`
  + `routing_precedence`. Full review: `.ai/ROUTING_PRECEDENCE_REVIEW.md`.
- **Local normalization** — Ollama responses are converted to OpenAI chat
  completion shape so downstream code (cache, metrics, cost estimation) is
  backend-agnostic (Decision 7).
- **Metrics** — every request records `RequestMetrics` (token deltas, latencies,
  cost estimate, applied optimizations) into `MetricsCollector`.

## Cross-cutting

- No heavy ML deps by default: sentence-transformers / LLMLingua / Redis /
  ollama are optional extras.
- Unknown model names fall back to `cl100k_base` tokenizer.
- Sync-only for v0.1 (async deferred).

## Architecture Knowledge Base (M14)

This file is the compact reference. The full permanent knowledge base lives
in `.ai/KNOWLEDGE_BASE/`:

- 01 System Overview · 02 Request Lifecycle · 03 Pipeline ·
  04 Provider Layer · 05 Configuration · 06 Metrics ·
  07 Architectural Contracts · 08 Extension Guide ·
  09 Internal Assessment (Software Factory view, ADB-11..13)

Start at `.ai/KNOWLEDGE_BASE/README.md`. The contracts in KB-07 are
normative; changing one requires an architecture decision
(`AGENTS.md` approval gate).
