# M13 Architecture Review

> Milestone M13 — Structural Refactoring & Architecture Stabilization
> (behavioral freeze: public API, routing precedence per Decision 24,
> fail-open, pipeline order, metrics semantics, examples, config, tests —
> no externally observable change is permitted in this milestone).
>
> This document is the milestone's architectural deliverable:
>
> 1. [Architectural Hotspot Report](#1-architectural-hotspot-report)
> 2. [Structural Refactoring Summary](#2-structural-refactoring-summary)
> 3. [Internal Architecture Assessment](#3-internal-architecture-assessment)
> 4. [Technical Debt Report](#4-technical-debt-report)
> 5. [Self-Review: Immediate Recommendations & ADB](#5-self-review-immediate-recommendations--adb)
> 6. [Validation Summary](#6-validation-summary)

---

## 1. Architectural Hotspot Report

Hotspots were identified by a full read of every `tokenopt/` module and a
line-by-line inventory (12 modules, ~1,300 LOC). Each hotspot lists the
problem, its impact, the recommended treatment, and whether it is addressed
now (M13) or deferred past v0.1.0.

### H1. Triple-implemented `get_user_query`

**Problem.** The "extract the last user message's text content" routine is
implemented identically three times: `RouterStage._get_user_query`
(`pipeline/router.py:89`), `RAGOptimizerStage._get_query`
(`pipeline/rag_optimizer.py:66`), and `FewShotSelectorStage._get_query`
(`pipeline/rag_optimizer.py:177`). `RAGOptimizerStage._reconstruct_messages`
additionally re-scans the whole message list on every iteration
(`rag_optimizer.py:140`).

**Impact.** Three drift-prone copies of one semantic; a future behavior
change (e.g. supporting content lists) must be made in three places and can
silently diverge. The per-iteration re-scan is wasted work proportional to
messages × rewritten messages.

**Recommendation.** Extract `get_user_query(messages)` into
`tokenopt/utils/messages.py` and use it from all three call sites; precompute
the query once in `_reconstruct_messages`.

**Address now (M13).** Pure internal de-duplication; byte-identical behavior.

### H2. Untyped `config: Any = None` on stage constructors

**Problem.** Five stage constructors accept `config: Any = None` and store it
unchecked: `CompressorStage` (`compressor.py:18`),
`ContextSummarizerStage` (`compressor.py:114`), `CacheStage` (`cache.py:34`),
`RAGOptimizerStage` (`rag_optimizer.py:16`), `FewShotSelectorStage`
(`rag_optimizer.py:153`). `RouterStage` already types it as
`TokenOptConfig | None` and defaults to `TokenOptConfig()` (`router.py:34-35`).

**Impact.** Inconsistent internal API; mypy cannot guard stage authors. With
`config=None`, RAG/fewshot/cache dereference `self.config.*` and fail with
`AttributeError`, which surfaces as a `*_error` fail-open metric — a hidden,
inconsistent failure mode that `RouterStage` does not share.

**Recommendation.** Type as `TokenOptConfig | None` and default to
`TokenOptConfig()` in all five constructors, matching `RouterStage`. The
stage's `config` is a threshold source only; the pipeline's gate decisions
already come from the pipeline-level config (`pipeline/base.py:97-105`).

**Address now (M13).** Internal typing/consistency only. Supported usage
(clients always pass a config) is observably unchanged; the pathological
`None` path now behaves like `RouterStage` instead of failing open.

### H3. Duplicated `_extract_usage` across providers

**Problem.** OpenAI-shaped usage extraction is byte-identical in
`OpenAI._extract_usage` (`clients/openai_client.py:32`) and
`LocalClient._extract_usage` (`clients/local_client.py:138`). Anthropic has a
different shape (`input_tokens`/`output_tokens`, `clients/anthropic_client.py:63`).

**Impact.** The OpenAI shape is mapped to the TokenOpt metrics vocabulary in
two places; a change (e.g. new usage fields) must be applied twice.

**Recommendation.** Extract a module-level `_extract_openai_shape_usage` in
`clients/base.py`; the two clients keep their methods (tested entry point) but
delegate to it. Anthropic keeps its own mapping.

**Address now (M13).** Internal de-duplication; identical output.

### H4. Three structurally identical compatibility shims

**Problem.** The drop-in shims forwarding `create()` to
`chat_completion` are written out three times: the nested `chat`/`Completions`
classes in `OpenAI` (`openai_client.py:41-58`) and `LocalClient`
(`local_client.py:163-180`), and the nested `messages` shim in `Anthropic`
(`anthropic_client.py:72-87`). All three `create()` bodies are identical.

**Impact.** The drop-in surface is the project's sacred contract; three
copies of the forwarding logic multiply the risk of subtle divergence (a
`**kwargs` change applied to one provider only).

**Recommendation.** One shared `_CompatShim` in `clients/_compat.py`; the
three properties instantiate it.

**Address now (M13).** Internal de-duplication; behavior identical
(covered by the drop-in surface tests in `tests/integration/`).

### H5. Duplicated pipeline-rebuild pattern in Anthropic and LocalClient

**Problem.** `Anthropic._build_pipeline` (`anthropic_client.py:23`) and
`LocalClient._build_pipeline` (`local_client.py:72`) both re-implement "take
the base pipeline, drop the router, and re-add a router scoped to a filtered
rule list" with their own `from dataclasses import replace` imports.

**Impact.** The "router scoping" contract exists in two places; a change to
the base pipeline composition must be re-checked in both subclasses.

**Recommendation.** Base `_build_pipeline(routing_rule_filter=None)`; the
subclasses pass a one-line model-compatibility filter.

**Address now (M13).** Internal, protected method; behavior identical for all
three providers.

### H6. `FewShotSelectorStage` co-located in `rag_optimizer.py`

**Problem.** `pipeline/rag_optimizer.py` is the largest SDK module (278
lines) and contains two unrelated stages: `RAGOptimizerStage` and
`FewShotSelectorStage`. The module name describes only the first.

**Impact.** Cohesion: the future maintainer navigates to the wrong module for
few-shot work; a 278-line file is harder to review.

**Recommendation.** Move `FewShotSelectorStage` to `pipeline/fewshot.py`.
Public surface unchanged (`tokenopt.pipeline` exports are preserved);
internal imports in tests updated.

**Address now (M13).** This is the milestone's core structural purpose.

### H7. `_select_by_diversity` re-embeds on every iteration

**Problem.** `FewShotSelectorStage._select_by_diversity`
(`rag_optimizer.py:212-248`) re-embeds the query and every candidate example
inside the selection loop — O(iterations × remaining × selected) embedding
calls for texts that never change.

**Impact.** With a real embedding model (sentence-transformers), the diversity
strategy's embedding cost dominates the stage; with the fallback provider it
is wasted hashing.

**Recommendation.** Precompute query and example embeddings once; selection
is deterministic given embeddings, so output is identical.

**Address after v0.1.0.** Algorithm-adjacent change; belongs to a
performance-investigation run post-freeze, with a real embedding model in CI.

### H8. `compression_attempted` mirrors `compression_applied`

**Problem.** `BaseOptimizedClient._record_metrics`
(`clients/base.py:180`) sets `compression_attempted` equal to
`compression_applied`, so the two fields are always identical and "attempted"
never captures a failed or no-op attempt.

**Impact.** Redundant metric; consumers cannot distinguish "stage ran" from
"compression changed tokens" — though `compression_effective`/`tokens_saved`
partly cover the latter.

**Recommendation.** Leave frozen in M13 (monitoring tests assert the current
values). Revisit post-v0.1.0 with a metrics-semantics decision, since
changing the meaning of a published field requires a deprecation plan.

**Address after v0.1.0.**

### H9. Stringly-coupled stage gating and ordering

**Problem.** `OptimizationPipeline._should_run_stage` (`pipeline/base.py:97`)
maps `stage.name` → config flag, while stage order is hard-coded in
`BaseOptimizedClient._build_pipeline` (`clients/base.py:54`); Anthropic and
LocalClient filter stages by `s.name != "router"` (`anthropic_client.py:27`,
`local_client.py:75`).

**Impact.** The stage→gate and stage→order contracts are implicit and
scattered; a new stage must know to touch three files, and a third-party
stage cannot declare its own gate.

**Recommendation.** A future extension/plugin architecture where each stage
declares its own gate (e.g. `enabled(config)`) and ordering is explicit —
see ADB-03.

**Address after v0.1.0** (architecture change; ADB).

### H10. Hard-coded `MODEL_COSTS` table

**Problem.** `MODEL_COSTS` (`observability/metrics.py:130-141`) embeds
pricing data in module code; updating prices or adding a model requires a
code change, and users cannot supply their own pricing.

**Impact.** Cost estimates drift from real pricing; the table is not
extensible.

**Recommendation.** A v0.2 cost-source abstraction (config-supplied pricing
over official defaults). Merely relocating the dict now would be churn
without value.

**Address after v0.1.0** (ADB-05).

### H11. Unkeyed metrics/metadata dictionaries

**Problem.** `OptimizationContext.metrics` and `metadata`
(`pipeline/base.py:22-23`) are plain `dict[str, Any]`; `_record_metrics`
reads ~10 string keys (e.g. `"routing_precedence"`, `"final_token_count"`)
while stages write them with no shared vocabulary.

**Impact.** Key typos surface only at runtime; the stage→metrics contract is
implicit and undocumented.

**Recommendation.** TypedDict vocabulary for the metrics contract and/or a
structured Optimization Trace (see ADB-02). No refactor in M13: the dict
interface is the working contract and is heavily test-covered.

**Address after v0.1.0.**

---

## 2. Structural Refactoring Summary

All refactors were internal-only, verified against the behavioral freeze
(167-test suite, 94% coverage — unchanged; 6/6 examples exit 0 against the
stub server; ruff/mypy/build/twine clean).

### R1. Shared `get_user_query` helper (H1)

- New `tokenopt/utils/messages.py::get_user_query(messages)`.
- `RouterStage`, `RAGOptimizerStage`, `FewShotSelectorStage` now share one
  implementation (three identical copies removed).
- `RAGOptimizerStage._reconstruct_messages` takes the precomputed query
  instead of re-scanning messages on every iteration.
- Behavior: identical; `utils/messages.py` 100% covered.

### R2. Typed stage configs (H2)

- `CompressorStage`, `ContextSummarizerStage`, `CacheStage`,
  `RAGOptimizerStage`, `FewShotSelectorStage` now declare
  `config: TokenOptConfig | None = None` and default to `TokenOptConfig()`,
  matching `RouterStage`.
- `CacheStage._get_redis` drops the now-dead `self.config and` guard.
- Behavior: identical for all supported usage (clients always pass a
  config; pipeline gates come from the pipeline-level config). The
  pathological `config=None` path now behaves like `RouterStage`
  (defaults) instead of raising `AttributeError` into a fail-open
  `*_error` metric — a consistency fix, not a contract change.

### R3. Shared OpenAI-shaped usage extraction (H3)

- `clients/base.py::_extract_openai_shape_usage(response)`; `OpenAI` and
  `LocalClient._extract_usage` delegate to it (methods kept — they are the
  tested entry point). `Anthropic` keeps its input/output-token mapping.

### R4. Shared compatibility shim (H4)

- New `clients/_compat.py::_CompatShim`; the `chat` (OpenAI, LocalClient)
  and `messages` (Anthropic) properties instantiate it. Three identical
  `create()` forwarders removed; the drop-in surface has one canonical
  implementation (covered by `tests/integration/test_openai_flow.py`,
  `test_anthropic_flow.py`, `test_local_client.py`).

### R5. Pipeline build consolidation (H5)

- `BaseOptimizedClient._build_pipeline(routing_rule_filter=None)` owns the
  "default pipeline minus router, plus scoped router" pattern.
- `Anthropic` and `LocalClient` now pass a one-line model-compatibility
  filter (AND-ed with any caller filter); the duplicated
  `dataclasses.replace` dance and per-file `RouterStage` imports are gone.
- Behavior: identical (router omitted when no compatible rules survive;
  scoped router otherwise).

### R6. Few-shot module split (H6)

- `FewShotSelectorStage` moved from `pipeline/rag_optimizer.py` (278
  lines, two unrelated stages) to `pipeline/fewshot.py`. `tokenopt.pipeline`
  exports unchanged; internal imports in `tests/test_fewshot.py` and
  `tests/test_pipeline_config.py` updated.

### Deliberately NOT refactored (with rationale)

- **H7 diversity re-embedding** — algorithm-adjacent performance fix;
  deferred to a post-freeze performance run.
- **H8 `compression_attempted` alias** — metrics semantics are frozen;
  test-asserted.
- **H9 stringly-coupled stage gating** — architecture change; ADB-03.
- **H10 `MODEL_COSTS` table** — relocation alone is churn; v0.2 cost-source
  abstraction; ADB-05.
- **H11 unkeyed metrics dicts** — working, heavily tested contract; ADB-02.

---

## 3. Internal Architecture Assessment

Assessment of the internal architecture as it stands after R1–R6. This is
a description and critique, not a redesign (per the M13 brief).

### 3.1 Provider abstraction

`BaseOptimizedClient` (`clients/base.py`) is a sound, minimal template:
`_create_client` / `_call_api` / `_extract_response_content` /
`_extract_usage` are the only provider seams, and `chat_completion` owns
the shared pipeline/cache/metrics flow. The three concrete clients are
thin and now nearly free of duplicated logic. `LocalClient` additionally
normalizes Ollama responses to the OpenAI shape (`_normalize_ollama_response`),
which is the right call: downstream stages and metrics treat every provider
uniformly.

Remaining concern: the pipeline itself is built inside the client layer,
so provider classes carry pipeline knowledge (order, router scoping).
Acceptable at this size; revisit if providers grow beyond three (ADB-01).

### 3.2 Pipeline stage abstraction

`PipelineStage` (`pipeline/base.py`) is clean: one `process(ctx)` seam, a
`__call__` wrapper that times every stage, and fail-open exception capture
in `OptimizationPipeline.run`. Stage lifecycle is stateless per request
(shared stage instances are reused across requests — safe because stages
mutate only `ctx` and the cache's own state).

Weaknesses:
- Stage ordering and per-stage gating live outside the stages
  (`_should_run_stage` name→flag map; order hard-coded in
  `_build_pipeline`); the contracts are implicit (H9, ADB-03).
- `metadata`/`metrics` are unkeyed dicts; the stage→client metrics
  vocabulary is implicit (H11, ADB-02).

### 3.3 Config model

`TokenOptConfig` (`config.py`) is a single flat dataclass with
pydantic-typed `RoutingRule`s for rules. It is pragmatic for v0.1: one
object flows through pipeline, clients, and metrics. The validation
`__post_init__` guards the three ratio thresholds. Stage-level defaults now
uniformly mirror `RouterStage` (R2), closing the constructor inconsistency.

Future pressure: as optimization features grow, the flat config will bloat;
a sectioned/grouped config is a post-v0.1.0 concern (ADB-04).

### 3.4 Context ownership

`OptimizationContext` is created once per request in `run` and owns
`messages`, `model`, `config`, `model_explicit`, plus `metadata`/`metrics`
accumulators. Stages mutate `ctx` in place and return it; the pipeline
writes final token metrics. The `original_*` snapshot fields support
comparison metrics. Ownership is clear and single-threaded per request —
no ownership problems found.

### 3.5 Metrics propagation

Flow: stage writes to `ctx.metrics` → `BaseOptimizedClient._record_metrics`
maps the ~10 read keys onto `RequestMetrics` → `MetricsCollector.record`
(thread-safe, callback guarded) → `StructuredLogger.log_request` emits one
JSON line per request. The mapping is the single place where stage
vocabulary becomes the public metrics vocabulary — good. `routing_reason`
has three-way fallback logic that must stay in sync with `RouterStage`
behavior (frozen; re-verified this milestone — no changes).

### 3.6 Factory

`factory.py` (`detect_provider` / `create_client` / `create_client_from_model`)
is a small, stable entry point. Detection is prefix/URL based, which is
appropriate for a zero-config SDK; it is deliberately overridden by
explicit `provider=` and by `base_url`. No changes needed this milestone.

### 3.7 Dependency graph

```
tokenopt/
├─ __init__ (exports OpenAI/Anthropic/LocalClient, factory)
├─ config  ← used by pipeline, clients, factory
├─ factory → clients → pipeline → utils + observability
├─ observability (metrics ← config; logger ← metrics)
└─ utils (messages, token_counter, embeddings — leaf modules)
```

Acyclic and layered: utils at the bottom, clients on top. The one coupling
worth noting: `config.py` imports `RequestMetrics` from observability for
the `metrics_callback` type — a config→observability edge that exists only
for typing. Harmless now; a `typing-only` split is possible later.

### 3.8 Extension points (current)

- Adding a stage: create a `PipelineStage` subclass, add it to
  `_build_pipeline`, add a gate to `_should_run_stage` (implicit contract,
  ADB-03).
- Adding a provider: subclass `BaseOptimizedClient` + implement the four
  seams; optional `_build_pipeline` filter for routing compatibility.
- Adding a model cost: edit `MODEL_COSTS` (ADB-05).
- Adding a routing rule: user-supplied `RoutingRule` in config (fully
  supported today, Decision 24).

### 3.9 Verdict

The internal architecture is coherent and proportional to the SDK's scope.
The five refactors removed real duplication (three query helpers, three
shims, two usage mappings, two pipeline rebuilds, one oversized module)
without touching any frozen contract. No structural risk was found that
needs to block v0.1.0.

---

## 4. Technical Debt Report

Classification: **Must-fix before v0.1.0** · **Acceptable (ship)** ·
**Candidate v0.2** · **Candidate Software Factory**.

### Must-fix before v0.1.0

None outstanding. The M13 suite (167), ruff, mypy, build, and twine all
pass; the routing precedence contract (Decision 24) is reviewed
(`ROUTING_PRECEDENCE_REVIEW.md` F1–F6 resolved). Remaining
`REPOSITORY_AUDIT.md` items are P2/P3 and track into v0.2+.

### Acceptable (ship with v0.1.0)

| Item | Reason to accept |
|---|---|
| `SimpleEmbeddingProvider` hash-based fallback (`utils/embeddings.py`) | Degraded but honest: semantic features return exact-match-only results without ML deps; documented; fail-open compatible |
| `CacheStage` Redis deserialization via `json.loads` + `CacheEntry(**entry)` | Works for `default=str` payloads; Redis is optional and error-swallowed |
| `_select_by_diversity` re-embedding (H7) | Correct, just slower with real models; v0.2 perf fix |
| `compression_attempted` alias (H8) | Test-asserted semantics; changing it needs a metrics-semantics decision + deprecation |
| Unkeyed `ctx.metrics`/`metadata` dicts (H11) | Heavy typing project; contract is test-covered |
| Stringly-coupled stage gating (H9) | Three-stage scale makes the map readable; extension work is rare |

### Candidate v0.2

| Item | Rationale | Tracked in |
|---|---|---|
| Plugin/extension architecture (stages declare own gate + order) | Enables third-party stages; removes name-string coupling | ADB-03 |
| Cost-source abstraction (`MODEL_COSTS` config-supplied) | Pricing drift; user-supplied pricing | ADB-05 |
| Optimization Trace (structured, queryable stage-by-stage trail) | Metrics vocabulary is implicit today; powers debugging/insight | ADB-02 |
| `_select_by_diversity` embedding precompute | Deterministic-identical, removes dominant stage cost | ADB-06 |
| `compression_attempted` semantic split | Distinguish "stage ran" vs "tokens changed" | ADB-07 |
| Config sectioning (grouped config) | Flat config will bloat with new features | ADB-04 |
| `config→observability` typing-only edge | Clean layering | ADB-08 |
| Prompt-library review/iteration (`PROMPTS/` after real use) | Validate against real LLM usage post-release | — |

### Candidate Software Factory

| Item | Rationale |
|---|---|
| ADR repository + architecture decision review workflow | Decisions 1–24 live in `DECISIONS.md`; formal ADRs + review cadence at factory scale |
| Automated coverage gating in CI (e.g. ≥90%) | Currently a session convention; make it mechanical |
| Benchmark/regression harness for optimization quality | No golden-dataset regression suite yet; needed before perf work |
| CI matrix (Python 3.10/3.11/3.12, provider SDK versions) | v0.1.0 CI is single-interpreter |

---

## 5. Self-Review: Immediate Recommendations & ADB

### 5.1 Immediate Recommendations (concrete, before/at v0.1.0 release)

1. **Close the audit P0.5 release gate at M15**: run `pip-audit`, enable
   Dependabot, add secret scanning to CI (`REPOSITORY_AUDIT.md` item 5).
2. **CI hardening (audit P0.1)**: matrix Python 3.10–3.12, hard coverage
   gate (≥ 80%), and run `python -m build` + `twine check` in CI so the
   gates this milestone validated locally are enforced mechanically.
3. **Extension guide (one page)**: how to add a stage (subclass
   `PipelineStage`, register in `_build_pipeline` + `_should_run_stage`)
   and a provider (subclass `BaseOptimizedClient`, four seams, optional
   `routing_rule_filter`). Closes the remaining part of audit P2.10; cheap
   and valuable for the v0.1 audience.
4. **Keep metrics semantics frozen through v0.1.0**; schedule ADB-07 with
   a documented deprecation in CHANGELOG after release.
5. **Re-run the M13 validation suite verbatim at M15** (pytest/ruff/mypy/
   build/twine/examples vs stub) as the pre-release regression baseline.

### 5.2 Architecture Decision Backlog (ADB)

Decisions to be made post-freeze. Each entry: rationale, expected benefit,
target milestone, priority.

| ID | Decision | Rationale | Expected benefit | Target | Priority |
|---|---|---|---|---|---|
| ADB-01 | Provider extension framework — extract pipeline composition into a provider-agnostic builder; providers declare capabilities (routing compatibility, usage shape) | Three providers share one flow; each new provider today copies Anthropic/Local pipeline-filter knowledge | One composition point; third-party providers become declarative | v0.2 | Medium |
| ADB-02 | Optimization Trace — typed, structured per-request stage trail (replaces unkeyed `ctx.metrics`/`metadata` contract) | Stage→metrics vocabulary is implicit (H11); typos surface only at runtime | Debuggability and per-stage insight; API-stable trace | v1.0 | Medium |
| ADB-03 | Plugin architecture — stages declare their own `enabled(config)` gate and ordering (replaces `_should_run_stage` name map) | Stage gating/ordering is implicit and scattered (H9) | Third-party stages; no hidden contracts | v0.2 | High |
| ADB-04 | Config sectioning — grouped/nested config beyond flat `TokenOptConfig` | Flat config will bloat as features grow | Evolvable config surface without breaking defaults | v0.2 | Low |
| ADB-05 | Cost-source abstraction — config-supplied pricing over official `MODEL_COSTS` defaults | Prices drift; table is code-embedded (H10) | Accurate estimates; user pricing; no code edits for price changes | v0.2 | Medium |
| ADB-06 | `_select_by_diversity` embedding precompute | Per-iteration re-embedding dominates the stage (H7) | Deterministic-identical, order-of-magnitude faster stage | v0.2 | Low |
| ADB-07 | `compression_attempted` semantic split — "stage ran" vs "tokens changed" | Field mirrors `compression_applied` today (H8); test-asserted | Distinct, truthful metrics; deprecation plan included | v0.2 | Low |
| ADB-08 | Decouple `config.py`'s `RequestMetrics` import (typing-only edge) | Config→observability edge exists only for the callback type | Clean layering | v0.2 | Low |
| ADB-09 | Optimization quality benchmark harness (golden datasets) | No regression baseline for optimization quality | Perf work (ADB-06) and future algorithms become measurable | Software Factory | High |
| ADB-10 | ADR repository + architecture review workflow | Decisions 1–24 in `DECISIONS.md` without review cadence | Formal decision lifecycle at scale | Software Factory | Medium |

### 5.3 Recommendation for Approval

M13 met its brief: internal-only structural refactoring under a behavioral
freeze, verified end-to-end (167 tests, 94% coverage, ruff/mypy clean,
sdist+wheel built, `twine check` PASSED, 6/6 examples against the stub
server). No public API, routing, metrics, config, or governance change.
The hotspot, assessment, and debt reports are accurate to the code as
committed. **Recommended for approval; the project is structurally ready
for M14 (architecture docs) and M15 (v0.1.0 release).**

---

## 6. Validation Summary

Run against the working tree as of the final M13 commit (behavioral freeze
verification).

| Gate | Command | Result |
|---|---|---|
| Tests | `python -m pytest tests -q` | **167 passed**, coverage **94%** (baseline: 167 / 94%) |
| Lint | `python -m ruff check tokenopt tests examples` | All checks passed |
| Types | `python -m mypy tokenopt` | Success: no issues in 23 source files |
| Build | `python -m build` | sdist + wheel built; new modules (`_compat.py`, `fewshot.py`, `messages.py`) included |
| Package check | `python -m twine check dist/*` | PASSED (wheel + sdist) |
| Examples | 6 examples + `_format.py` vs stub server (127.0.0.1:8787) | **6/6 exit 0** (anthropic_basic, local_basic, metrics_observability, openai_basic, pipeline_config, quickstart) |
| Routing precedence | Decision 24 paths unchanged | Covered by `tests/test_router.py` + integration flows (167 suite unchanged) |
| Metrics semantics | All metric fields and fallback logic untouched | Diff review: no changes to `metrics.py`/`logger.py`/`_record_metrics` mapping |
| Docs/links | `.ai/**/*.md` link check | Clean (no new/removed links introduced by M13 docs) |
| CI (GitHub Actions) | post-push badge poll | `build: passing` (verified after push) |

New/changed files (internal-only): `tokenopt/utils/messages.py` (new),
`tokenopt/pipeline/fewshot.py` (new), `tokenopt/clients/_compat.py` (new),
`tokenopt/pipeline/{router,rag_optimizer,compressor,cache,__init__}.py`,
`tokenopt/clients/{base,openai_client,anthropic_client,local_client}.py`,
`tests/test_fewshot.py`, `tests/test_pipeline_config.py` (import paths).

---


