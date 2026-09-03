# 01 — System Overview

*Part of the [Architecture Knowledge Base](README.md).*

## Project goals

TokenOpt is a Python SDK that makes LLM interactions cheaper, faster, and
more context-efficient — as a **drop-in replacement** for OpenAI, Anthropic,
and local model servers.

```python
from tokenopt import OpenAI          # instead of: from openai import OpenAI
```

Users change one import and get automatic optimization: routing,
compression, summarization, semantic caching, RAG-chunk optimization, and
few-shot selection, with built-in metrics and structured logging
(`Decision 1`).

Design constraints:

- **Python ≥ 3.10**, sync-only for v0.1 (async deferred).
- **No heavy defaults**: ML and optional-provider dependencies live behind
  optional extras (`tokenopt[semantic]`, `tokenopt[local]`, Redis, etc.).
- **Offline, deterministic tests**: integration tests use
  `httpx.MockTransport`, never live APIs (`Decision 15`).

## Architectural philosophy

The SDK is a **wrapper over a pipeline**: a thin provider client exposes the
native API surface while every request flows through the same optimization
pipeline. Three principles rule:

1. **The drop-in contract is sacred** — the public surface
   (`OpenAI`, `Anthropic`, `LocalClient`, `create_client*`) mirrors the
   underlying SDKs (`chat.completions.create(...)`, `messages.create(...)`).
   Public API changes are additive-only and always user-approved
   (`Decisions 14, 19`).
2. **Providers are thin, normalization is centralized** — clients only
   translate provider quirks; everything downstream (pipeline, cache,
   metrics, cost) works on one normalized shape (`Decision 7`).
3. **Optimization is conservative and transparent** — every optimization is
   individually gated by configuration, every applied optimization is
   recorded in metrics, and nothing is ever applied that cannot be turned
   off.

## Fail-open philosophy

Optimization must **never break the underlying request**
(`Decision 21`, hardened in M3):

- A stage that raises inside the pipeline is caught, recorded as
  `{stage}_error` in the metrics dictionary, and the request continues with
  unoptimized messages. The caller never sees the stage error.
- Routing must never send a request to a model the provider cannot serve:
  the router is scoped per provider (`Decisions 8, 13`) and never rewrites
  an explicit caller model (`Decision 24`).
- Metrics callbacks and logging are themselves guarded — observability can
  never break the main flow.
- The only errors the caller sees are genuine **provider API errors**, and
  even those are recorded as metrics before re-raising.

Corollary for contributors: a new optimization that can fail must fail into
an *unoptimized* path, never an *error* path.

## Optimization philosophy

- **Order is contract**: the router runs first (model choice precedes
  token work, which is tokenizer-specific), then compression, then
  summarization, then caching, then RAG, then few-shot. See
  [03 — Pipeline](03_PIPELINE.md).
- **Each optimization is opt-out, not opt-in**: sensible defaults are on,
  users disable per-stage (`enable_compression`, `enable_routing`, ...).
- **Degrade gracefully without optional dependencies**: compression falls
  back from LLMLingua to heuristics; embeddings fall back from
  sentence-transformers to a deterministic hash provider; caching falls
  back from Redis to in-memory. A missing optional package degrades the
  feature, never the request.
- **Token work targets the routed model's tokenizer** — an unknown model
  name falls back to the `cl100k_base` encoding (`Decision 10`).

## Routing philosophy

Routing selects the most cost-effective model for each request:

- **Rule-based + complexity scoring**: user-supplied (and built-in) rules
  match on the query; when no custom rules are configured, a keyword +
  token-count heuristic picks a complexity tier.
- **Least surprise** (`Decision 24`): an explicit caller model is never
  overridden; a rule that does not match never rewrites the model; the
  complexity heuristic only applies to users who configured nothing.
- **Provider safety**: rules are model-compatible with the provider — the
  Anthropic adapter only honors `claude-*` rules, local only non-cloud
  rules — so routing can never produce an invalid model for the endpoint.
- **Every decision is recorded**: `routing_precedence`
  (`explicit | rule | preserve | complexity | provider_default`) plus the
  rule name / complexity tier in metrics and logs.

## Package structure

```
tokenopt/
├── __init__.py          # public API surface
├── config.py            # TokenOptConfig, RoutingRule, get_default_config()
├── factory.py           # create_client / create_client_from_model / detect_provider
├── clients/
│   ├── base.py          # BaseOptimizedClient — shared request flow (pipeline + metrics)
│   ├── _compat.py       # _CompatShim — one canonical drop-in shim implementation
│   ├── openai_client.py # OpenAI drop-in
│   ├── anthropic_client.py
│   └── local_client.py  # Ollama (native) / vLLM / llama.cpp / LM Studio (OpenAI-compatible)
├── pipeline/
│   ├── base.py          # OptimizationContext, PipelineStage, OptimizationPipeline
│   ├── router.py        # RouterStage
│   ├── compressor.py    # CompressorStage, ContextSummarizerStage
│   ├── cache.py         # CacheStage (+ CacheEntry)
│   ├── rag_optimizer.py # RAGOptimizerStage
│   └── fewshot.py       # FewShotSelectorStage
├── observability/
│   ├── metrics.py       # RequestMetrics, MetricsCollector, estimate_cost, MODEL_COSTS
│   └── logger.py        # StructuredLogger, JsonFormatter
└── utils/
    ├── messages.py      # get_user_query (shared stage helper)
    ├── token_counter.py # tiktoken counting/truncation
    └── embeddings.py    # EmbeddingProvider + SimpleEmbeddingProvider fallback
```

Dependency direction is acyclic and layered: `utils` ← `pipeline` /
`observability` ← `clients` ← `factory`/`__init__`, with `config` shared by
all layers.
