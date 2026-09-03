# 03 — Pipeline

*Part of the [Architecture Knowledge Base](README.md).*

## Execution order (contract)

Fixed order, declared in `BaseOptimizedClient._build_pipeline`
(`tokenopt/clients/base.py`) and documented in
`.ai/ARCHITECTURE.md`:

```
1. RouterStage          model selection (cheapest/smartest)
2. CompressorStage      prompt compression (heuristic or LLMLingua)
3. ContextSummarizerStage  conversation-history summarization
4. CacheStage           semantic cache lookup (exact + similarity)
5. RAGOptimizerStage    RAG chunk dedup/rerank/filter
6. FewShotSelectorStage few-shot example selection
```

Why this order:

- **Router first**: model choice precedes any token work, because token
  counting/compression targets the routed model's tokenizer, and routing
  influences cost metrics recorded later.
- **Compression before summarization**: summarization is a coarse fallback
  for history that compression cannot shrink; compression first means the
  summarizer sees the tightest possible input (and its token threshold is
  checked on compressed content).
- **Cache lookup near the end but before generation**: the cache key must
  reflect the fully optimized prompt (compressed/summarized messages), so
  hits match on what would actually be sent. The API call happens after the
  pipeline, and the response is stored back post-call (write-through).
- **RAG then few-shot**: both embed against the query and mutate messages;
  running RAG first means few-shot selection sees the final user query
  context.

## Stage responsibilities

| Stage | Input | Work | Writes to `ctx` |
|-------|-------|------|-----------------|
| RouterStage | query (last user message) | precedence contract (`Decision 24`): explicit wins; rule match by priority; preserve on custom-no-match; complexity heuristic as default | `model`, `metrics["routing_*"]` |
| CompressorStage | all messages | LLMLingua (optional) else heuristic (whitespace, fillers, truncation to `compression_ratio` × original tokens) | `messages`, `metrics["compression_applied"]` |
| ContextSummarizerStage | history > `summarization_threshold` tokens | system-message-preserving summary of history; keeps last 3 messages | `messages`, `metrics["summarization_applied"]`, `summarized_messages` |
| CacheStage | normalized prompt | exact-key lookup, Redis lookup (optional), in-memory similarity search | `metadata["cache_hit"]` / `cached_response` / `cache_key` / `prompt_embedding` |
| RAGOptimizerStage | messages with `context:`/`retrieved:` blocks or `rag_chunks` | chunk extraction, embedding scoring, threshold filter, near-dup removal, max-chunk cap | `messages`, `metrics["rag_*"]` |
| FewShotSelectorStage | query + configured examples | similarity / diversity / random selection; inject after system message | `messages`, `metrics["fewshot_*"]` |

## Stage interactions

- **Shared query helper**: stages read the last user message through one
  implementation, `utils/messages.py::get_user_query` (M13 R1) — the query
  semantics cannot drift between router, RAG, and few-shot.
- **Shared embeddings**: RAG and few-shot use the same embedding provider
  instance pattern (`get_embedding_provider(fallback=True)`); cache shares
  it too. The fallback provider makes exact-match-only semantics explicit
  when sentence-transformers is absent.
- **Token counting**: compressor and pipeline metrics count with the
  current (possibly routed) model's tokenizer via
  `utils/token_counter.py`; unknown models fall back to `cl100k_base`
  (`Decision 10`).
- **Message mutation is serial**: each stage receives the previous stage's
  messages; final metrics are computed on the post-pipeline messages.

## Fail-open behavior

- `OptimizationPipeline.run` wraps each stage call in `try/except`; a stage
  raising produces `ctx.metrics[f"{stage.name}_error"]` and execution
  continues with the previous stage's output.
- Consequences for stage authors: a stage must never rely on having
  mutated `ctx` for downstream correctness of the *call* (a later stage can
  fail open too); the request is always sendable with the messages that
  reached the end.
- The client boundary only re-raises **provider API errors** (see
  [02 — Request Lifecycle](02_REQUEST_LIFECYCLE.md)).

## Gating

`OptimizationPipeline._should_run_stage` maps stage names to config flags
(`pipeline/base.py`):

| Stage | Gate (config field) |
|-------|---------------------|
| compressor | `enable_compression` |
| cache | `cache_enabled` |
| router | `enable_routing` |
| summarizer | `enable_summarization` |
| rag_optimizer / fewshot | always on (no gate field) |

Note: the gate uses the **pipeline-level config**, while stage thresholds
read the stage's own config — identical objects in normal operation (M13 R2
made stage defaults consistent with `RouterStage`).

## Context lifecycle

`OptimizationContext` (`pipeline/base.py`):

- Created **per request** in `run()`; owned by that request only.
- `__post_init__` snapshots `original_messages` (deep-enough copies) and
  `original_token_count` — the comparison baseline for savings metrics.
- `metadata` carries request kwargs; `metrics` accumulates stage outputs.
- Every stage call is timed by `PipelineStage.__call__`, writing
  `{stage}_latency_ms` — per-stage latency is free.
- `run()` finishes by writing `final_token_count`, `token_reduction`,
  `token_reduction_pct` — the pipeline's summary vocabulary consumed by the
  client's metric mapper.
- Stages never own the context beyond the call; the client reads it once
  for metrics and cache storage.

## Pipeline construction

- Base composition in `BaseOptimizedClient._build_pipeline`; provider
  subclasses pass a `routing_rule_filter` (M13 R5) so the router only sees
  model-compatible rules (Anthropic: `claude*`; local: non-cloud). The
  router stage is omitted entirely when no compatible rules survive.
- `OptimizationPipeline` holds the stage list and the config; it is built
  once per client and reused for every request (stages must be stateless
  across requests except their own caches — the cache stage owns its LRU).
