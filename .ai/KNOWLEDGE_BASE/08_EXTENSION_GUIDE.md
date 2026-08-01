# 08 — Extension Guide

*Part of the [Architecture Knowledge Base](README.md).*

Guidance for safely extending TokenOpt. **Principles first; nothing here
changes runtime code.** Each recipe lists the exact seams to touch, the
contracts to respect, and the tests to add.

## Extension principles

1. **Preserve contracts first** — read
   [07 — Architectural Contracts](07_ARCHITECTURAL_CONTRACTS.md) before
   touching anything; if the change touches a contract, stop and raise an
   architecture decision instead.
2. **Additive-only** — new fields, new metrics, new kwargs, new stages.
   Never redefine existing behavior or response shapes.
3. **Fail open** — new optimizations must degrade to the unoptimized path;
   new dependencies must be optional extras with clear errors.
4. **One owner, one gate** — every optimization knob belongs to
   `TokenOptConfig` (flat, validated); stages are gated by the pipeline's
   `_should_run_stage` map.
5. **Small, tested, documented** — one logical change; unit + integration
   tests; KB/contract docs updated in the same milestone.

## Adding a provider

1. Subclass `BaseOptimizedClient` (`tokenopt/clients/base.py`).
2. Implement the four seams: `_create_client`, `_call_api`,
   `_extract_response_content`, `_extract_usage` (map provider usage to
   `{prompt_tokens, completion_tokens, total_tokens}`).
3. If the endpoint cannot serve models matched by generic rules, pass a
   model-compatibility filter to `_build_pipeline(routing_rule_filter=...)`
   (see Anthropic/local for the pattern).
4. Normalize the response to the OpenAI chat shape if the provider is
   non-OpenAI-shaped (see the normalization contract, C8).
5. Expose the native drop-in surface via `_CompatShim` (`chat` or
   `messages` property).
6. Register in `tokenopt/__init__.py`, `factory.py` (`detect_provider` +
   `create_client`), and the KB provider doc.
7. Tests: drop-in surface, response extraction (success + error), usage
   mapping, router scoping, metrics fields — follow the pattern of
   `tests/test_local_client.py` + `tests/integration/`.

## Adding a pipeline stage

1. Subclass `PipelineStage` (`tokenopt/pipeline/base.py`); set `name`.
2. Implement `process(ctx)` — read/write `ctx.messages`, `ctx.model`,
   `ctx.metrics`; return `ctx`. Do not raise: leave failure to the
   pipeline's fail-open guard (record a metric key if useful).
3. Respect the context lifecycle: never mutate anything outside `ctx`;
   never hold per-request state on the stage (stages are reused).
4. Register it:
   - order + construction in `BaseOptimizedClient._build_pipeline`;
   - gate in `OptimizationPipeline._should_run_stage` (name → config flag)
     when the stage should be switchable;
   - export from `tokenopt/pipeline/__init__.py`.
5. Write facts to `ctx.metrics` with a stage-prefixed key vocabulary
   (e.g. `{name}_applied`, `{name}_latency_ms` is automatic).
6. Tests: `tests/test_<stage>.py` behavioral contract (inputs →
   `ctx.metrics`/`ctx.messages`), gating test in `test_pipeline_config.py`,
   fail-open test (stage raising → `{name}_error`, request continues).

## Extending metrics

1. Add an **additive** field to `RequestMetrics` (`observability/metrics.py`)
   with a default — never redefine existing fields (contract C5).
2. Populate it in the single mapper `_record_metrics` (`clients/base.py`)
   from `ctx.metrics` (preferred: have the producing stage write the key).
3. Surface it in `StructuredLogger.log_request` if it should appear in JSON
   logs; in `get_summary()` only if it is an aggregate.
4. Tests: extend `tests/integration/test_metrics_clarity.py` + the relevant flow test;
   assert the field appears in `get_recent`/callback/log line.

## Extending configuration

1. Add a flat field with a sane default to `TokenOptConfig`
   (`tokenopt/config.py`); add range validation to `__post_init__` when it
   is a ratio/probability.
2. Wire consumers: stage threshold or `_should_run_stage` gate.
3. Document in `05_CONFIGURATION.md` (group table) and README when
   user-facing.
4. Do **not** add env-var or global configuration (contract C7); do not
   section the config (ADB-04 is the planned vehicle for that).
5. Tests: default value, validation edge cases, gating behavior.

## Adding an optimization stage

Same recipe as "adding a pipeline stage", plus:

- Place it in the order that matches its dependencies (token work after
  routing; message mutation before cache look-up if it must affect cache
  keys; see contract C4 rationale).
- Make it conservative: default-on with a gate; degrade without optional
  deps; never touch `ctx.model` (that is the router's job).
- Demonstrate value in an example script before claiming it.

## What requires approval (do not implement without it)

- Changing a contract (C1–C8), public API, routing behavior, metrics
  semantics, config ownership, package structure, or adding dependencies.
- New functionality beyond additive optimization stages.
- Anything the M13/M14 reviews flagged as deferred (ADB-01..13).
