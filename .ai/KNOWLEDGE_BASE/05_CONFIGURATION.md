# 05 — Configuration

*Part of the [Architecture Knowledge Base](README.md).*

## Configuration hierarchy

There is exactly one configuration object: `TokenOptConfig`
(`tokenopt/config.py`), a flat dataclass. It is owned by the caller and
passed to the client constructor:

```
Caller ── TokenOptConfig ──► client (config)
                              ├─ pipeline (OptimizationPipeline.config)
                              ├─ each stage (stage.config)
                              └─ observability (metrics_callback)
```

Precedence within a request:

1. **Request kwargs** (`chat_completion(**kwargs)`) — provider call
   arguments; never configuration overrides.
2. **Client-constructor config** — the single source of behavior.
3. **Defaults** — dataclass field defaults + `get_default_config()`.

There is no environment-variable configuration and no nested/grouped
config today; per-group sectioning is a tracked future opportunity
(ADB-04).

## Configuration groups

| Group | Fields |
|-------|--------|
| Compression | `compression_ratio` (0.5), `enable_compression` (True) |
| Caching | `cache_enabled` (True), `cache_ttl` (3600s), `cache_similarity_threshold` (0.95), `cache_max_size` (10000), `redis_url` (None) |
| Routing | `enable_routing` (True), `routing_rules` ([]), `default_model` (`gpt-4o-mini`) |
| Summarization | `enable_summarization` (True), `summarization_threshold` (8000), `summarization_model` (`gpt-4o-mini`) |
| RAG | `rag_max_chunks` (5), `rag_similarity_threshold` (0.7) |
| Few-shot | `fewshot_max_examples` (3), `fewshot_selection_strategy` (`similarity`) |
| Observability | `observability_enabled` (True), `metrics_callback` (None) |

## Defaults

- Field defaults are conservative: optimizations enabled, thresholds
  sensible, optional integrations (`redis_url`) off.
- `get_default_config()` additionally seeds three **built-in routing
  rules**, each marked `RoutingRule.builtin=True`:

| Rule | Priority | Routes to |
|------|----------|-----------|
| `simple_queries` | 10 | `gpt-4o-mini` (short, non-analytical queries) |
| `code_tasks` | 20 | `gpt-4o` (code/function/debug/refactor/implement) |
| `reasoning_tasks` | 30 | `o1-mini` (reason/step-by-step/think/logic/proof) |

The `builtin` flag matters: routing precedence treats only non-builtin
(custom) rules as "custom routing configuration" (`Decision 24`), so a
user who never touches rules still gets built-in complexity routing on
no-match — default-config behavior is unchanged by the flag.

## Overrides

- **Whole-config override**: pass a constructed `TokenOptConfig` to the
  client — used by every example (e.g. `examples/pipeline_config.py`
  demonstrates OFF/ON comparisons and custom rules).
- **Factory convenience**: `create_client(model=...)` synthesizes
  `TokenOptConfig(default_model=model)` when no config is passed.
- **Stage-level defaults**: stages default to `TokenOptConfig()`
  consistently (M13 R2) — a stage constructed standalone behaves like the
  pipeline stage with defaults; the pipeline's own gates always use the
  pipeline-level config.

## Validation

`TokenOptConfig.__post_init__` rejects out-of-range ratios:

- `compression_ratio` ∈ (0, 1]
- `cache_similarity_threshold` ∈ (0, 1]
- `rag_similarity_threshold` ∈ (0, 1]

`RoutingRule` is a pydantic model (`name`, `condition` callable, `model`,
`priority`, `builtin`) — structural validation at construction, custom
logic left to the user.

## Extension strategy

- **New optimization knobs**: add a field with a sane default to
  `TokenOptConfig`, wire it in the stage (threshold) and in
  `_should_run_stage` (gate) when the stage should be switchable.
- **New routing rules**: user-supplied `RoutingRule` objects — fully
  supported today; no config change required (the documented extension
  point of the routing system).
- **Custom metrics handling**: `metrics_callback` receives every
  `RequestMetrics`; consumers implement their own sinks.
- **Do not** add environment-variable or global configuration without an
  architecture decision — the single-config-object ownership is a
  contract (see [07 — Architectural Contracts](07_ARCHITECTURAL_CONTRACTS.md)).
- Sectioned/grouped configuration is deferred (ADB-04) — any new field
  should keep the flat shape to remain compatible.
