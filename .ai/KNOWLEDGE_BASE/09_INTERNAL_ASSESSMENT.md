# 09 — Internal Assessment

*Part of the [Architecture Knowledge Base](README.md).*

Assessment from the perspective of the future **Software Factory**: what is
reusable today, what limits reuse, and where the system can grow.
**This section describes; it does not redesign.** (M13's full assessment and
debt report: `.ai/M13_ARCHITECTURE_REVIEW.md` §3–§4.)

## Current architecture — strengths

| Strength | Where |
|----------|-------|
| Layered, acyclic dependency graph | `utils` → `pipeline`/`observability` → `clients` → `factory`; `config` shared |
| Single request entry point per client | `chat_completion` — complete instrumentation by construction |
| Thin providers + one normalization shape | pipeline/cache/metrics are provider-agnostic (C6/C8) |
| Single metrics mapper | `_record_metrics` guarantees stage facts and public metrics agree (C5) |
| Fail-open by construction | per-stage guard, guarded callbacks, provider-scoped routing (C3) |
| Testable + deterministic | offline integration tests, 167 tests / 94% coverage, behavioral freeze proven in M13 |
| Documented decision record | Decisions 1–25; routing review; M13 architecture review |

## Current architecture — limitations

| Limitation | Where | Tracked as |
|------------|-------|------------|
| Stringly-coupled stage gating/ordering | `_should_run_stage` name map; order hard-coded in `_build_pipeline` | ADB-03 |
| Unkeyed `ctx.metrics`/`metadata` dicts — implicit vocabulary | `pipeline/base.py`; `_record_metrics` reads ~10 keys | ADB-02 |
| Flat single config object | `config.py` — grows with every feature | ADB-04 |
| Cost data embedded in code | `MODEL_COSTS` in `observability/metrics.py` | ADB-05 |
| `compression_attempted` mirrors `compression_applied` | `clients/base.py` | ADB-07 |
| Diversity selection re-embeds per iteration | `pipeline/fewshot.py` | ADB-06 |
| Pipeline composition knowledge lives in the client layer | `clients/base.py` | ADB-01 |
| `config.py` imports `RequestMetrics` (typing-only edge) | config → observability | ADB-08 |

## Reusable components (for the Software Factory)

1. **The pipeline framework** — `PipelineStage`/`OptimizationPipeline`:
   timed stage calls, fail-open guard, per-request context, final token
   metrics. Reusable as-is for new optimization families.
2. **The metrics vocabulary + mapper pattern** — stages-write, client-maps,
   collector-aggregates is a repeatable contract pattern.
3. **The response-normalization contract** — one canonical shape for
   arbitrary LLM backends (currently OpenAI shape).
4. **The governance OS** — `.ai/` (manifest, workflows, roles, prompts,
   standards, index) is itself the first reusable factory component.
5. **Deterministic offline test infrastructure** — `httpx.MockTransport`
   integration harness pattern (`Decision 15`).

## Reusable patterns

- Template-method provider (four seams + shared flow).
- Fail-open wrapper (stage guard; guarded callback).
- Optional-dependency degradation (`try/import` extras, fallback
  providers, clear errors).
- Additive-only API evolution (new fields/kwargs, never redefinitions).
- Timed-decorator stage (`PipelineStage.__call__` latency instrumentation).

## Future extension points

- **Stage-gate declaration** (ADB-03): stages declare `enabled(config)` and
  ordering — removes the name map.
- **Provider capability declarations** (ADB-01): providers declare routing
  compatibility, usage shape, normalization needs — removes
  subclass-override knowledge.
- **Optimization Trace** (ADB-02): typed, queryable per-stage record —
  the basis for a debugging/insight surface.
- **Cost-source abstraction** (ADB-05): config-supplied pricing over
  official defaults.
- **Internal architecture contracts** (ADB-11): formalize pipeline
  lifecycle, context ownership, metrics ownership, cache lifecycle, and
  provider abstraction as testable contracts.
- **Machine-readable architecture manifest** (ADB-12): the KB as
  structured data for orchestration systems.

## Future opportunities (ADB-11 .. ADB-13)

### ADB-11 — Internal Architecture Contracts (required addition, M14)

Formalize the internal seams as **testable contracts** post-v0.1.0:

- **Pipeline lifecycle** — stage init/process/cleanup lifecycle,
  ordering guarantees, gate declaration.
- **Context ownership** — rules for who may read/mutate
  `OptimizationContext`, what stages may own.
- **Metrics ownership** — typed vocabulary (TypedDict/Trace), mapper
  invariants, additive-only enforcement.
- **Cache lifecycle** — key derivation, TTL, eviction, Redis
  serialization invariants.
- **Provider abstraction** — the four seams + normalization shape as
  abstract contracts with conformance tests.

- Rationale: today these invariants are documented and test-covered
  implicitly; formal contracts make them machine-verifiable and let the
  Software Factory validate extensions mechanically.
- Expected benefit: extension safety, automated contract testing,
  orchestration-ready guarantees.
- Priority: **High**. Target milestone: **v0.2** (post-v0.1.0).

### ADB-12 — Machine-readable architecture manifest

Emit the KB's normative content (components, seams, contracts C1–C8,
metrics vocabulary) as structured data (JSON/YAML) that orchestration
systems and agents can validate extensions against.

- Rationale: the Software Factory consumes machines, not prose; today the
  contracts live only in markdown.
- Expected benefit: automated extension validation, tooling integration.
- Priority: **Medium**. Target milestone: **Software Factory**.

### ADB-13 — Response-normalization contract enforcement

Make the LocalClient→OpenAI normalization shape a validated model
(schema-checked `SimpleNamespace`/dataclass) instead of an informal
shape.

- Rationale: the normalization contract (C8) is honored by convention;
  a malformed backend response currently surfaces downstream.
- Expected benefit: earlier, clearer failures; stronger drop-in
  guarantees for new local backends.
- Priority: **Medium**. Target milestone: **v0.2**.

## Verdict

The architecture is coherent, layered, and extension-shaped: the hardest
parts (contracts, fail-open, provider seams) are already explicit and
test-covered. The identified limitations are growth pains, not faults —
each has a tracked ADB item with a target milestone. No redesign is
recommended before v0.1.0.
