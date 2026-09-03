# CHECKPOINT 2026-08-01 — Pre-M13 Routing Precedence Decision

**Milestone:** Pre-M13 architecture decision — RouterStage precedence
**Status:** DONE (implemented + verified)
**Decision:** 24 (see `.ai/DECISIONS.md`; review: `.ai/ROUTING_PRECEDENCE_REVIEW.md`)

## Completed work

- **Review** (`.ai/ROUTING_PRECEDENCE_REVIEW.md`): findings F1 (rule
  provenance), F2 (explicit-model detection), F3 (provider clients),
  F4 (empty-query path), F5 (fail-open), F6 (routing_reason); compatibility
  impact table; recommendation.
- **Contract implemented (5 levels, least surprise)**:
  1. Explicit caller model — never overridden
  2. Matching routing rule (custom + built-in, priority order)
  3. Custom rules exist but none match → **preserve caller's model**
  4. No custom routing configuration → built-in complexity routing
  5. Provider default (resolved model stands)
- **Code changes**:
  - `tokenopt/config.py` — `RoutingRule.builtin: bool = False`; the 3
    default rules marked builtin (only user rules count as "custom" for
    precedence 3 vs 4 → default-config behavior unchanged)
  - `tokenopt/pipeline/router.py` — precedence logic; records
    `routing_precedence` on every path; empty-query no longer overwrites
  - `tokenopt/pipeline/base.py` — `OptimizationContext.model_explicit`;
    `OptimizationPipeline.run(model_explicit=False, ...)`
  - `tokenopt/clients/base.py` — `chat_completion(model_explicit=None)`
    (additive); `_record_metrics` maps `routing_reason` (+
    "preserved (no rule matched)") and `routing_precedence`
  - `tokenopt/clients/local_client.py` — explicitness pass-through
  - `tokenopt/observability/metrics.py` — `RequestMetrics.routing_precedence`
    (additive)
  - **Fix**: no-match with custom rules no longer rewrites to `gpt-*` on
    Anthropic/local backends (invalid-model break → fail-open, Decision 21)
- **Tests** (158 → **167**): test_router.py +5 new / 4 updated;
  test_metrics_clarity.py +2 new / 2 updated; test_anthropic_flow.py
  +1 new / 1 updated; test_openai_flow.py 1 updated (implicit model).
- **Examples**: pipeline_config.py reworked (rule matches + preserved
  no-match + complexity-only + OFF vs ON); `_format.py` explain() prints
  "Routing kept X (preserved (no rule matched))". Validated against the
  stub server in a clean venv: **6/6 exit 0, output matches docstrings**.
- **Docs**: ARCHITECTURE.md (contract section), README (precedence list),
  CHANGELOG ([Unreleased] Added routing_precedence + Changed precedence).

## Modified files

- SDK: `tokenopt/{config,clients/base,clients/local_client,pipeline/base,
  pipeline/router,observability/metrics}.py`
- Tests: `tests/test_router.py`, `tests/integration/{test_metrics_clarity,
  test_anthropic_flow,test_openai_flow}.py`
- Examples: `examples/pipeline_config.py`, `examples/_format.py`
- Docs: `README.md`, `CHANGELOG.md`, `.ai/ARCHITECTURE.md`,
  `.ai/DECISIONS.md` (+24), `.ai/ROUTING_PRECEDENCE_REVIEW.md` (new),
  memory files

## Commit hashes

- <pending> — `feat: routing precedence contract (Decision 24)`
- <pending> — `test: routing precedence contract unit tests`
- <pending> — `test: routing precedence integration tests`
- <pending> — `docs: routing precedence review and decision`
- <pending> — `docs: update examples for routing precedence`
- <pending> — `chore: update memory and checkpoint`

## Blockers

None. M13 refactor can proceed.

## Architecture decisions made

- Decision 24: routing precedence contract (5 levels, provenance via
  `RoutingRule.builtin`, explicit-model tracking, routing_precedence
  metric)

## Next tasks

1. M13 — maintainability refactor (behavior-preserving): response
   helpers, data-driven MODEL_COSTS
2. M14 — architecture docs polish (Mermaid, normalization spec,
   extension guide)
3. M15 — release v0.1.0 (tag, notes, optional PyPI ⚠)

## Exact prompt to continue in a new session

> The pre-M13 routing precedence decision is complete and implemented:
> Decision 24 (five-level contract; explicit caller model wins, matching
> rule wins, custom rules with no match preserve the caller's model,
> no custom rules → complexity routing, provider default last).
> `RoutingRule.builtin` marks the SDK's default rules; `model_explicit`
> plumbing (OptimizationContext/pipeline.run/chat_completion) tracks
> explicit models; RouterStage records `routing_precedence`;
> `RequestMetrics.routing_precedence` is additive; `routing_reason`
> gains "preserved (no rule matched)". Review:
> `.ai/ROUTING_PRECEDENCE_REVIEW.md`. Suite 167 green; examples
> validated 6/6 against the stub server; commits pushed (verify `git
> log` + CI badge passing).
> Continue with **M13** (maintainability refactor — behavior-preserving:
> response helpers, data-driven MODEL_COSTS). Follow
> `.ai/IMPLEMENTATION_ROADMAP.md`, the refactoring workflow
> (`.ai/WORKFLOWS/refactoring.md`) + backend-engineer role, AGENTS.md
> gates (pytest 167, ruff, mypy), then update memory, create
> CHECKPOINT_20260801_M13.md, commit, push (verify remote =
> https://github.com/rohit-naik36/TokenOpt.git), confirm CI green.
