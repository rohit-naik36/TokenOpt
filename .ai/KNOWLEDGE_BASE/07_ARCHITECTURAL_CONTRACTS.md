# 07 — Architectural Contracts

*Part of the [Architecture Knowledge Base](README.md).*

These are **guarantees**, not implementation details. Each contract records
what must never break, why it exists, and where it is enforced/verified.
Contracts are append-only: relaxing one requires an architecture decision
and a recorded rationale (approval gate per `AGENTS.md`).

## C1. Public API stability (drop-in contract)

**The contract.** `tokenopt.OpenAI`, `tokenopt.Anthropic`,
`tokenopt.LocalClient`, and the factory surface mirror the underlying SDKs:
`client.chat.completions.create(...)`, `client.messages.create(...)`, and
`chat_completion(...)` behave exactly like their native counterparts —
including the shape of the returned response object. Public API changes are
**additive-only** and user-approved (`Decisions 1, 14, 19`).

**Why.** The entire value proposition is "change one import". Every
deviation is a silent migration cost for users; a broken response shape
breaks user code.

**Enforced by.** Drop-in surface tests (`tests/integration/`),
`tests/test_local_client.py`; the single shared `_CompatShim` (M13 R4);
`README.md` documented surface; M13 behavioral freeze verification.

## C2. Routing precedence (Decision 24)

**The contract.** The router decides in exactly five levels:
(1) explicit caller model — never overridden; (2) matching rule by
priority — first match wins; (3) custom rules exist but none match — the
caller's requested model is **preserved**, never rewritten; (4) no custom
routing configuration — built-in complexity routing; (5) provider default —
the resolved model stands. Every decision records `routing_precedence` and,
where applicable, `routing_rule`/`routing_complexity`.

**Why.** The previous complexity fallback silently rewrote caller models
and produced invalid `gpt-*` models on Anthropic/local endpoints — breaking
fail-open and surprising users. Least surprise: explicit intent wins, rules
route only when they match, heuristics only serve users who configured
nothing.

**Enforced by.** `tests/test_router.py` (precedence matrix),
`tests/integration/test_anthropic_flow.py`, `test_openai_flow.py`,
`test_metrics_clarity.py` (integration suite); review in
`.ai/ROUTING_PRECEDENCE_REVIEW.md`.

## C3. Fail-open philosophy

**The contract.** Optimization must never break the underlying request.
Pipeline stage failures are swallowed and recorded as `{stage}_error`
metrics; observability failures are swallowed; only genuine provider API
errors propagate to the caller (and those are recorded first). A failed
optimization degrades to the unoptimized path, never an error path.

**Why.** Optimization is a value-add; the request is the product. A cache
bug or missing optional package must not take down production calls
(`Decision 21`, M3 hardening, `Decision 16` for optional dependencies).

**Enforced by.** Pipeline fail-open tests (`tests/test_pipeline_config.py`,
`test_cache.py` error paths); error-path tests in `test_openai_flow.py` /
`test_anthropic_flow.py` (API errors recorded + re-raised);
callback-guard tests.

## C4. Pipeline execution order

**The contract.** All six stages run in the fixed order
router → compressor → summarizer → cache → rag → fewshot, per request,
each individually gated. The router runs first; the cache look-up sees the
fully optimized prompt; generation happens after the pipeline.

**Why.** Stage order encodes real dependencies (tokenizer-dependent token
work after routing; cache keys must match what would be sent; few-shot
after RAG so it embeds the final query context). Reordering silently
changes optimization outcomes and metrics.

**Enforced by.** `_build_pipeline` composition; stage-order assertions in
`tests/test_pipeline_config.py`; `examples/pipeline_config.py` (OFF/ON
demonstrations).

## C5. Metrics ownership

**The contract.** Stages write facts to `ctx.metrics`; the client's
`_record_metrics` is the single mapper to `RequestMetrics`; the collector
aggregates and never sees pipeline keys; metric vocabulary is
**additive-only** (never redefined). `routing_reason` is derived only from
router-written keys (`Decision 20`).

**Why.** A single mapping point keeps stage facts and public metrics
provably consistent; additive-only changes keep consumers and monitoring
stable; the routing_reason rule prevents the report from contradicting the
router's decision.

**Enforced by.** `tests/integration/test_metrics_clarity.py`; integration flow tests
asserting field values against stub-server responses.

## C6. Provider abstraction

**The contract.** Providers implement the four seams (`_create_client`,
`_call_api`, `_extract_response_content`, `_extract_usage`) plus optional
router scoping (`_build_pipeline(routing_rule_filter)`). Responses are
normalized to one shared shape (Ollama → OpenAI shape, `Decision 7`);
providers never route to models their endpoint cannot serve
(`Decisions 8, 13`).

**Why.** Thin providers + centralized normalization mean the pipeline,
cache, and metrics are provider-agnostic by construction; router scoping
prevents invalid-model calls (fail-open). The template also makes adding
providers a documented, low-risk exercise ([08 — Extension Guide](08_EXTENSION_GUIDE.md)).

**Enforced by.** Abstract-method tests; `test_local_client.py` +
integration flows per provider; normalization assertions on Ollama-shaped
responses.

## C7. Configuration ownership

**The contract.** Behavior is controlled by exactly one `TokenOptConfig`
object owned by the caller; stage defaults are consistent with it (M13 R2);
there is no environment-variable or global configuration. New knobs are
flat fields with sane defaults and range validation.

**Why.** One object is inspectable, serializable, and testable — and
guarantees the pipeline gates and stage thresholds can never disagree (they
refer to the same instance). Global/env config would break the drop-in
philosophy and the deterministic test suite.

**Enforced by.** `test_pipeline_config.py` (gate mapping),
`test_config` validation tests, examples passing explicit configs.

## C8. Local response normalization

**The contract.** Every local backend yields the OpenAI chat-completion
shape (`choices[0].message.content`, `usage` with prompt/completion/total
tokens) — see [04 — Provider Layer](04_PROVIDER_LAYER.md). Downstream
components never special-case backends.

**Why.** Without it, cache keys, metrics, and cost estimation would need
per-backend branches (Decision 7); the contract keeps the whole pipeline
single-path.

**Enforced by.** `test_local_client.py` (Ollama-shaped response
normalization), `tests/integration/test_local_client_flow.py`.

## How contracts change

A contract change is an **architecture decision**: it requires the
architecture-review workflow, a recorded rationale in `.ai/DECISIONS.md`,
explicit user approval, and coordinated test/doc updates. The M13
behavioral freeze demonstrated the discipline: refactors that would have
touched contracts (metrics alias, stage gating) were documented and
deferred instead of implemented.
