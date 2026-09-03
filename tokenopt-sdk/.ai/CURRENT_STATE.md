# TokenOpt SDK — Current State

_Last updated: 2026-08-01 (M1–M8 + UAT + M8.2 + M10 + M11 + M12 + M13 + M14 complete; next is M15)_

## Status: Phase 0 + Phase 1 + M1–M8 + Post-M8 UAT refinements + M8.2 + M10 + M11 + M12 complete

A Python SDK for token/prompt optimization wrapping OpenAI/Anthropic clients as
drop-in replacements, plus local model servers (Ollama/vLLM/llama.cpp).

## Complete

- **Project setup** — `pyproject.toml` (valid TOML, numpy added to required deps,
  optional extras: cache/semantic/compression/local/dev/all; explicit
  `[tool.setuptools] packages`; ruff config in correct sections)
- **Core modules**
  - `tokenopt/config.py` — `TokenOptConfig`, `RoutingRule`, `get_default_config()`
  - `tokenopt/utils/` — tiktoken counting (`count_tokens`, `count_message_tokens`,
    `truncate_to_tokens`), embedding providers (sentence-transformers + fallback)
- **Pipeline stages** (`tokenopt/pipeline/`) — `OptimizationPipeline` framework +
  compressor, summarizer, semantic cache (LRU + optional Redis), router,
  RAG optimizer, few-shot selector
- **Observability** — `MetricsCollector`, `RequestMetrics`, `estimate_cost()`,
  structured JSON logger
- **Clients** (`tokenopt/clients/`)
  - `BaseOptimizedClient` — pipeline integration, metrics, cache wiring
  - `OpenAI` — drop-in for `openai.OpenAI`
  - `Anthropic` — drop-in for `anthropic.Anthropic`
  - `LocalClient` — Ollama/vLLM/llama.cpp, backend auto-detected from base_url,
    Ollama responses normalized to OpenAI chat shape
- **Factory** (`tokenopt/factory.py`) — `create_client()`, `create_client_from_model()`,
  `detect_provider()` (model prefix / base_url detection)
- **Package exports** — `tokenopt/__init__.py`, `tokenopt/clients/__init__.py`
- **Tests** — 23 unit tests passing (imports, LocalClient, factory)
- **Git** — repo initialized on `main`, 12+ logical commits; working tree clean;
  pushed to `https://github.com/rohit-naik36/TokenOpt.git`
- **Project memory** — `.ai/` structure created, checkpoints taken
- **Project manifest** — `.ai/PROJECT_MANIFEST.md` ratified (constitution:
  overview, product definition, technical vision, engineering standards,
  git strategy, workflow, DoD, AI agent rules, conventions, release process,
  long-term vision)
- **Agent manual** — root `AGENTS.md` created (tool-agnostic operating manual:
  responsibilities, startup procedure, dev rules, docs rules, git rules,
  checkpoint rules, approval gates, session close, continuous improvement)
- **AI Engineering Foundation (Phase 0, M0.1–M0.3)** — `.ai/STANDARDS/`
  (8 normative standards), `.ai/WORKFLOWS/` (5 runbooks), `.ai/ROLES/`
  (4 role definitions); manifest + AGENTS.md updated to reference them
- **Implementation roadmap** — `.ai/IMPLEMENTATION_ROADMAP.md` approved with
  Phase 0 modification; awaiting approval to begin M1 (fix mypy gate)
- **Session management (Decision 12)** — `.ai/SESSION_STATE.md` +
  `.ai/TASK_QUEUE.md` maintained; controlled shutdown at 01:12
- **Packaging** — `pip install -e .` verified, `python -m build` OK; README exists
- **Lint** — `ruff check tokenopt tests` fully clean (fixed 64+ findings incl.
  one latent bug: missing import in `pipeline/compressor.py`)
- **M1 — Verification Gates complete (2026-08-01)**
  - `mypy tokenopt` now exits 0 (was broken: numpy 2.5 stubs vs py3.10 target)
  - **numpy pinned `>=1.24,<2.5`** in `pyproject.toml` (2.5 requires
    Python ≥ 3.12, incompatible with declared `>=3.10`; stubs use PEP 695
    syntax mypy can't parse under `python_version=3.10`)
  - mypy overrides for optional extras (`redis.*`, `llmlingua.*`,
    `sentence_transformers.*` — `ignore_missing_imports`) so the gate works
    without installing heavy optional deps
  - Fixed **37 real typing findings** across 11 files (no behavior change)
  - Fixed **latent runtime bug**: `ContextSummarizerStage.__init__` accepted
    a callable but `BaseOptimizedClient` passed the config positionally —
    summarization would have crashed calling the config object (now
    `config` + optional `summarizer_fn` params, matching all other stages)
  - Fixed wrong `metrics_callback` type annotation in `config.py`
    (runtime contract: callback receives `RequestMetrics`, not `dict`)
  - Created `.ai/DOD.md` — permanent Definition of Done with the 5-gate
    verification pipeline (pytest, ruff, mypy, build, fresh-venv smoke)
  - AGENTS.md, README, git/coding standards updated to include `mypy` gate
- Full gate verified: 23 tests pass, ruff clean, mypy 0, build OK,
  wheel installs + imports in a fresh venv
- **M2 — Pipeline Stage Unit Tests (2026-08-01)**
  - `tests/test_router.py` (18 tests) — priority-ordered custom/default rules,
    complexity fallback (keywords + token thresholds), empty/malformed queries,
    rule-exception fail-open, determinism, no shared-state mutation
  - `tests/test_compressor.py` (16 tests) — heuristic path (whitespace, filler
    removal, per-message truncation), LLMLingua stub for ML path + fail-open
    fallback on ML failure, lazy-load gating (`sys.modules` stub), edge cases
  - `tests/test_summarizer.py` (13 tests) — threshold gating, ≤2/≤3-message
    no-ops, custom `summarizer_fn`, extractive fallback, system-message
    reconstruction, malformed content, determinism, no mutation
  - `tests/test_pipeline_config.py` (5 tests) — enable/disable gating per stage
    via `OptimizationPipeline` (defaults on, independent switches)
  - **Defect found + fixed (minimal)**: `ContextSummarizerStage` kept the
    *first* 3 non-system messages as recent and summarized the *newest* ones
    (opposite of the documented "Keep last 3 messages" intent); latest user
    query could be summarized away. Fixed to keep the last 3 and summarize
    older history (no API change).
  - Coverage: `router.py` 27% → **100%**, `compressor.py` → **100%**
    (summarizer included), suite total 62% → **72%**
  - Suite: **77 tests passed** (54 new); ruff clean; mypy exit 0
- **M3 — Pipeline Stage Tests 2 (2026-08-01)**
  - `tests/test_cache.py` (18 tests) — miss/store/exact-hit roundtrip; stats
    and hit counts; LRU eviction at `cache_max_size`; TTL expiry (exact +
    semantic paths); semantic hit/miss at threshold (scripted provider);
    model-mismatch no-hit; Redis roundtrip + failure fail-open (fake clients);
    `clear()`; non-string content; determinism; no mutation
  - `tests/test_rag_optimizer.py` (15 tests) — extraction (`context:`/
    `retrieved:` + `rag_chunks` key); relevance ranking/threshold; `rag_max_chunks`
    cap; dedup near-duplicates; no-context/no-query no-ops; malformed content;
    determinism; no mutation
  - `tests/test_fewshot.py` (13 tests) — similarity/diversity/random
    strategies; max-examples caps; injection order/format after system;
    metrics; determinism; no mutation
  - `tests/test_pipeline_config.py` (+7) — cache gating (enabled/disabled);
    RAG/few-shot always-on by default; **pipeline fail-open**
  - **4 defects found + fixed (minimal, no API change)**:
    1. Cache key collision — non-string message content (e.g. multimodal
       lists) normalized to identical empty keys → different prompts could
       cross-hit. Now serialized via `json.dumps(sort_keys=True)`.
    2. RAG dedup embedding misalignment — `_deduplicate_chunks` received
       `chunk_embeddings[:len(filtered)]` (original order) after chunks were
       re-sorted by relevance → wrong chunk/embedding pairs compared, valid
       chunks dropped. Embeddings now carried through the sort.
    3. Few-shot injection dropped when no system message — `fewshot_applied`
       claimed success but nothing was injected. Examples now prepended.
    4. Pipeline stage exceptions propagated → request failure, violating
       fail-open (manifest design principle 3). `OptimizationPipeline.run`
       now catches per-stage errors and records `{stage}_error` metric.
  - Coverage: `cache.py` 68% → **96%**, `rag_optimizer.py` 24% → **98%**,
    suite total 72% → **89%**
  - Suite: **130 tests passed** (53 new); ruff clean; mypy exit 0
- **M4 — Integration Tests & Coverage Gate (2026-08-01)**
  - `INTEGRATION_TEST_STRATEGY.md` (repo root) — definition of integration
    tests, offline execution policy, provider isolation mechanics, coverage
    gate, determinism rules
  - `tests/integration/` (19 tests, zero new dependencies — Decision 15):
    - `conftest.py` — `httpx.MockTransport` handlers (OpenAI/Anthropic/500
      payloads) + request-recording fixtures + client fixtures
    - `test_openai_flow.py` (8) — full drop-in flow (routing → compression →
      call → metrics), request-body optimization, cache-hit short-circuit
      (1 provider call for 2 identical requests), provider 500 re-raise +
      error metrics, stage failure fail-open end-to-end, disabled compression
      passthrough, metrics callback, factory roundtrip
    - `test_anthropic_flow.py` (5) — full messages flow (max_tokens default
      + passthrough), system-message split into `system` param, gpt-targeted
      default rules filtered, custom claude routing rule, cache short-circuit,
      provider error metrics
    - `test_local_client_flow.py` (5) — OpenAI-compatible backend full flow
      (model/messages passthrough), cache short-circuit, provider error,
      Ollama backend end-to-end (fake `ollama` module + transport), factory
  - **2 genuine integration defects found + fixed (minimal, Decisions 13–14)**:
    1. `chat` property nesting — documented drop-in surface
       `client.chat.completions.create(...)` raised `AttributeError`
       (`chat.create` only). Fixed in `openai_client.py` + `local_client.py`
       to mirror the real SDK (`chat.completions.create`).
    2. Anthropic adapter broken out of the box — default config routed
       requests to `gpt-4o-mini`, sending a nonexistent model to the
       Anthropic API. Fixed: router scoped to claude-targeted rules
       (Decision 13, mirrors LocalClient precedent Decision 8).
  - **Coverage gate**: `[tool.coverage] fail_under = 80` +
    `addopts = --cov=tokenopt` in `pyproject.toml` — enforced by pytest itself
  - Suite: **149 tests passed** (19 new); coverage **94%**; ruff clean;
    mypy exit 0; build OK
- **M5 — Continuous Integration (2026-08-01)**
  - `.github/workflows/ci.yml` — triggers: push to main, PRs,
    `workflow_dispatch`; `concurrency` cancel-in-progress; least-privilege
    permissions. Three jobs, fail-fast:
    1. `lint` (3.12) — `ruff check tokenopt tests` + `mypy tokenopt`
    2. `test` (matrix 3.10/3.11/3.12) — `pip install -e ".[dev]"` +
       `pytest tests/` (coverage ≥80% gate from M4 enforced in CI)
    3. `package` (3.12, after test) — `python -m build` + fresh-venv wheel
       install + `import tokenopt` smoke (DoD gate 5) + dist artifact upload
  - `CONTRIBUTING.md` (new) — dev setup, DoD gates, CI layout/assumptions,
    branch protection recommendations (user-administered settings)
  - README — CI badge + "Continuous Integration" section
  - **CI executed and verified via GitHub API: full matrix green**
    (run 30664914071: lint ✅, test 3.10/3.11/3.12 ✅, package ✅)
  - **2 genuine CI-found defects fixed (minimal, Decision 16)**:
    1. `mypy tokenopt` failed in CI on `import ollama` (local env had the
       optional package installed, masking it) — `ollama.*` added to the
       optional-extras mypy overrides in `pyproject.toml`
    2. `create_client(provider="local")` crashed with a bare
       `ModuleNotFoundError` when `ollama` is not installed — `_create_client`
       now raises a clear `RuntimeError` with `pip install tokenopt[local]`
       hint; factory tests no longer depend on the optional package
       (+1 regression test, `tests/test_factory.py`)
  - Suite: **150 tests passed**; coverage **94%**; ruff clean; mypy exit 0
- **M6 — Release Metadata (2026-08-01)**
  - **MIT LICENSE** (user decision; Copyright (c) 2026 rohit-naik36)
  - **CHANGELOG.md** — Keep a Changelog format, SemVer, `[Unreleased]` +
    `[0.1.0] - 2026-08-01` (Added: all core functionality; Fixed: the 8
    defects found in M1–M5)
  - **pyproject.toml metadata completed** (Decision 17): author
    `rohit-naik36`, enriched description, 12 keywords, 9 classifiers
    (Alpha, MIT via PEP 639 SPDX `license = "MIT"`, Python 3.10–3.12,
    OS Independent, AI/ML topics), `[project.urls]` (Homepage/Repository/
    Issues/Documentation/CI — verified against `git remote -v`), build
    floor `setuptools>=77` (PEP 639). No runtime functionality changed.
  - **README release-readiness review**: added "Supported providers &
    features" table (OpenAI/Anthropic/Local + feature list), "Optional
    extras" section, "Status" (pre-1.0, fails open), License → MIT link
  - **Packaging verified**: `python -m build` sdist+wheel ✅; `twine check`
    PASSED for both artifacts ✅; fresh-venv wheel install + `import tokenopt`
    ✅; installed metadata verified via `importlib.metadata` (version 0.1.0
    matches `tokenopt.__version__`, License-Expression MIT, 9 classifiers,
    5 URLs, 6 runtime deps + extras); sdist ships LICENSE + README
  - Suite: **150 tests passed**; coverage **94%**; ruff clean; mypy exit 0
- **M7 — Security Baseline (2026-08-01)** (Decision 18)
  - **Author metadata personalized** (prerequisite): `pyproject.toml`
    `authors = ["Rohit Naik"]` + LICENSE copyright — verified in built wheel
    (`Author: Rohit Naik`, `License: MIT`); repo ownership/URLs unchanged
  - **pip-audit** in `dev` extra + CI `security` job: `pip-audit --path . --desc`
    — local scan (2.10.1): **0 known vulnerabilities**; tokenopt itself
    skipped (not on PyPI, expected)
  - **gitleaks** pinned **8.30.1** (standalone binary, not a pip dep) in CI:
    `detect --log-opts=--all` full-history — local scan: **58 commits, no leaks**
  - **Dependabot** `.github/dependabot.yml`: weekly `pip` + `github-actions`
    updates (numpy ≥2.5 ignored); activated immediately — 3 update PRs
    opened (checkout/setup-python/upload-artifact → v7), advisory only
  - **SECURITY.md**: supported versions, private reporting (7/14-day
    timelines), scope (in/out), coordinated disclosure (90-day), release
    **blocker vs advisory** classification table
  - **CONTRIBUTING.md**: security job + local reproduction commands
  - CI run 30666354747: **all green** (lint, security, test ×3, package)
  - No SDK functionality changed (tooling/CI/docs only)
- **M8 — Developer Onboarding & Experience (2026-08-01)**
  - **examples/** (6 ruff-clean scripts): quickstart (drop-in), openai_basic
    (config + cache-hit demo), anthropic_basic (messages API), local_basic
    (endpoint env-overridable), pipeline_config (routing rules + complexity
    fallback), metrics_observability (callback + cost + token utils)
  - **README rewritten**: Quick Start, Installation (git install until PyPI,
    core + 7-extras table), provider examples, factory, configuration,
    project structure tree, **Troubleshooting/FAQ (9 entries)** — FAQ claims
    verified against stage code, dev/CI/security/status/license sections
  - **Makefile**: help/install/dev/lint/typecheck/test/coverage/build/audit/
    smoke/clean mirroring CI
  - **CONTRIBUTING.md**: M8 note removed; Makefile + examples documented
  - **Clean-environment validation**: fresh venv + `pip install -e .`; all 6
    examples executed against a local OpenAI/Anthropic-compatible stub server
    (temp, uncommitted) — exit 0, routing + cache hit + anthropic + local +
    callback verified; `pip install git+...` dry-run ✅; all 5 extras
    `--dry-run` resolve ✅
  - **Defect fixed**: `metrics_observability.py` F821 forward-ref
    `"RequestMetrics"` → real import (public API unchanged)
  - Suite: **150 passed**; coverage **94%**; ruff clean (incl. examples);
    mypy exit 0; build + twine check PASSED
- **Post-M8 UAT Refinements (2026-08-01)** (session 12)
  - **Metrics clarity (additive)**: `RequestMetrics` +
    `compression_attempted`/`compression_effective`/`tokens_saved`/
    `reduction_percentage` + `model_latency_ms` (inference time); populated
    in `base._record_metrics`; JSON log enriched; `compression_applied`
    kept (documented as "stage ran")
  - **Example output**: `examples/_format.py` (quiet + print_request +
    print_summary); all 6 examples → readable blocks (Model, Cache hit,
    Compression attempted/effective, Tokens, Latency total|model|overhead,
    Estimated cost, Response); local_basic = miss→hit demo + per-instance
    cache note
  - **README**: 5-Minute Quick Start (7 steps + expected output)
  - **docs/UAT.md**: permanent manual release acceptance checklist
    (10 scenario groups + sign-off)
  - **Regression tests**: 5 new (`tests/integration/test_metrics_clarity.py`)
  - **CHANGELOG [Unreleased]**: Changed entries
  - Suite: **155 passed**; coverage **94%**; ruff clean; mypy exit 0;
    build + twine PASSED; CI badge passing
- **M8.2 — Value Demonstration & Showcase (2026-08-01)** (session 13)
  - **`RequestMetrics.routing_reason`** (additive field, Decisions 19–20):
    populated in `base._record_metrics` from `ctx.metrics` — matched rule
    name (e.g. `math_tasks`) else `complexity-based (low|medium|high)`;
    RouterStage remains the single source of truth (`routing_rule` /
    `routing_complexity` keys)
  - **examples/_format.py**: `explain(metrics)` — why-lines derived ONLY
    from recorded metrics (cache hit, compression effective/attempted,
    summarization, routing_reason, overhead vs model latency split);
    `print_comparison(title, before, after)` — OFF vs ON side-by-side
  - **6 examples rewritten as value demonstrations**: header docstrings
    ("Demonstrates / Expected outcome"), realistic long prompts:
    - quickstart — drop-in + compression + routing reason + summary
    - openai_basic — compression OFF (331→331, 0%) vs ON (331→184,
      ~44%), then cache miss→hit on a separate client
    - anthropic_basic — 5-turn conversation, threshold 150 → summarization
      applied (167→140), claude model untouched
    - local_basic — multi-paragraph code-review prompt (164→89, ~46%),
      miss→hit; cloud routing rules auto-skipped for local backends
    - pipeline_config — 4 prompts, 4 routing decisions (simple→gpt-4o-mini
      complexity-based (low), code→gpt-4o (medium), math→o1-mini
      math_tasks rule, complex→gpt-4o (high)) + routing OFF vs ON
    - metrics_observability — every metric annotated field-by-field,
      latency-split story (miss 157.8 ms overhead vs hit 0.3 ms), callback
  - **README**: example sections now describe demonstrated value
    (compression OFF vs ON, cache miss→hit, summarization, routing reasons,
    observability); **CHANGELOG [Unreleased]**: Added routing_reason +
    Changed examples/README entries
  - **Regression tests**: +3 (`routing_reason` rule match / complexity
    fallback / disabled) in `tests/integration/test_metrics_clarity.py`
  - **Clean-environment validation** (fresh venv + stub server at
    127.0.0.1:8787): all 6 examples exit 0; printed explanations
    cross-checked against recorded metrics — all truthful; routing_reason
    verified live (`math_tasks`, `complexity-based (low|medium|high)`)
  - Commits `203b3d4` (feat), `ec4f638` (examples), `2a6093f` (README/
    CHANGELOG); suite **158 passed**; coverage **94%**; ruff clean
    (incl. examples); mypy exit 0; build + twine PASSED; pushed to main
  - Truthfulness notes: quickstart prompt was edited to remove "I think"
    (the default `reasoning_tasks` rule matches the substring "think",
    routing the demo to o1-mini); header claims match measured values
    (44.4% vs "~44%")
- **M10 — AI Engineering Governance Expansion (2026-08-01)** (session 14;
  Decision 21; no SDK changes)
  - **Review (Phase 1)**: 8 inconsistencies found + fixed (I1–I8):
    stale "(mypy after M1 fix)" in implement-feature; divergent
    verification blocks per workflow; release.md "maintainer" owner that
    didn't exist; fix-bug missing checkpoint standard; no DOD links;
    ROADMAP count drift; IMPLEMENTATION_ROADMAP M10 pre-execution scope;
    no workflow/role registry
  - **WORKFLOWS/ 5 → 14**: unified template (purpose, prerequisites,
    steps, verification, expected outputs, completion criteria); 9 new:
    refactoring, architecture-review, documentation-update,
    dependency-upgrade, security-response, performance-investigation,
    uat-execution, regression-verification, repository-audit; all gates
    standardized to pytest + ruff + mypy
  - **ROLES/ 4 → 11**: extended template (authority, required inputs,
    success criteria); 7 new: product-strategist, product-manager,
    qa-engineer, security-reviewer, release-manager, devops-engineer,
    repository-auditor; single-owner matrix (no overlap)
  - **`.ai/GOVERNANCE_INDEX.md`** — machine-consumable registry:
    role↔workflow↔standard tables, ownership matrix, single approval
    gate, handoff map (Idea → Software Factory substrate)
  - **`.ai/GOVERNANCE_REVIEW.md`** — review summary + multi-agent
    validation (no circularity/conflicts; deterministic order; handoffs)
  - **Consistency fixes**: AGENTS.md points to the index; ROADMAP Phase 0
    counts + M10 done; IMPLEMENTATION_ROADMAP M10 = executed scope, M9
    marked "covered by M0.1" (never executed separately); DECISIONS +21
  - **Verification**: link check over 64 md files (all resolve); workflow
    owners all resolve to real roles; suite 158 green; ruff/mypy clean;
    SDK/tests/examples/README untouched
  - Commits: `72ddef0`, `76a83b4`, `588d182`, `e49d6c1`, `2cf461f`,
    `104d366` (memory commit follows); pushed to main; CI green
- **M11 — AI Prompt Library (2026-08-01)** (session 15; Decision 22;
  no SDK changes)
  - **`.ai/PROMPTS/` grouped by purpose**: `design/` (architecture-review),
    `implementation/` (feature, bug-fix, refactoring, unit-testing),
    `verification/` (integration-testing, regression-verification),
    `operations/` (documentation-update, release-preparation,
    repository-audit) — **10 prompts**
  - **Template (per prompt)**: objective, required inputs, deterministic
    numbered instructions (exact commands/paths), expected outputs,
    verification criteria (executable checkboxes), determinism rules
    (never/always constraints)
  - **`.ai/PROMPTS/README.md`** — prompt design guidelines: grouping table,
    template spec, determinism rules (evidence over memory, exact
    commands, one judgment-call limit, composable handoffs), layer model
    (prompt = execution / workflow = runbook / role = ownership /
    standard = normative rule), add + maintenance rules (append-only,
    live-after-use)
  - **Cross-references**: GOVERNANCE_INDEX gains a Prompts table (prompt →
    group → owner → governing workflow); every prompt links its workflow
    + role + standards; IMPLEMENTATION_ROADMAP M11 marked done;
    ROADMAP +21? no — DECISIONS +22
  - **Verification**: link check over 75 md files (all resolve); prompt →
    workflow/role cross-refs 10/10 resolve; suite 158 green; ruff/mypy
    clean; SDK/tests/examples untouched
- **M12 — Repository Curation (2026-08-01)** (session 16)
  - **Deleted (regenerated)**: `dist/`, `tokenopt.egg-info/`, `.coverage`,
    `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, 8× `__pycache__/`
  - **Deleted (duplicates/disposable)**: 7 empty artifact dirs
    (`C?ProjectsNew/`, `Idea_Factory/`, `Projecttests/`,
    `Projecttokenopt{clients,observability,pipeline,utils}/`)
  - **Archived**: `SESSION_BACKUP.md` → `.ai/ARCHIVE/` (`git mv`, history
    intact) — audit finding 9 closed
  - **Added**: `.ai/REPOSITORY_INVENTORY.md` (classification + deletion
    ledger), `.ai/REPOSITORY_RETENTION_POLICY.md` (permanent / archived /
    regenerated / disposable / user-owned), `.github/` PR template + issue
    templates (bug, feature) + CODEOWNERS (single-maintainer posture)
  - **Updated**: REPOSITORY_AUDIT.md §7 dated closure (findings 6, 9 + plan
    item 8 closed), GOVERNANCE_INDEX Policies section, repository-audit
    workflow (curation step + retention-policy prerequisite)
  - **Verification**: link check 79/79 resolve; git history intact (85
    commits, rename detected); suite 158 green; ruff/mypy clean;
    SDK/tests/examples untouched; root tree contains only intentional
    entries
- **Pre-M13 — Routing Precedence Decision (2026-08-01)** (session 17;
  Decision 24; SDK change)
  - **Contract (5 levels, least surprise)**: 1) explicit caller model
    never overridden; 2) matching rule (custom + built-in) wins by
    priority; 3) custom rules exist but none match → preserve the
    caller's model; 4) no custom rules → built-in complexity routing;
    5) provider default (resolved model stands)
  - **Implementation**: `RoutingRule.builtin` flag (default rules marked,
    only user rules count as "custom" — default-config behavior
    unchanged); `OptimizationContext.model_explicit` + pipeline.run +
    `chat_completion(model_explicit=...)` plumbing; RouterStage records
    `routing_precedence` on every path; `RequestMetrics.routing_precedence`
    (additive); `routing_reason` gains "preserved (no rule matched)"
  - **Fix**: no more `gpt-*` rewrite on no-match for custom rules —
    eliminates invalid-model calls on Anthropic/local backends (fail-open)
  - **Tests**: test_router.py +8 net (explicit wins, custom no-match
    preserve, builtin-only complexity, mixed); metrics_clarity +2
    (preserved reason, explicit never overridden) +2 updated;
    anthropic_flow +1 (no-match preserves explicit model) +1 updated;
    openai_flow updated (implicit model for routing demo) — suite
    **167 passed**
  - **Examples**: pipeline_config.py reworked to demonstrate the
    precedence contract (math→o1-mini rule, code→gpt-4o rule,
    preserved no-match ×2, complexity-only config, OFF vs ON);
    _format.py explain() reports "Routing kept X (preserved ...)" —
    validated against stub server 6/6 exit 0, output truthful
  - **Docs**: `.ai/ROUTING_PRECEDENCE_REVIEW.md` (findings F1–F6,
    compatibility, recommendation), ARCHITECTURE.md contract section,
    README precedence list, CHANGELOG entry
  - **Verification**: 167 passed, ruff clean, mypy green, examples
    truthful, CI green
- **M13 — Structural Refactoring & Architecture Stabilization (2026-08-01)**
  (session 18; Decision 25; internal-only, behavioral freeze)
  - **Hotspots (H1–H11)**: triplicated `get_user_query`; untyped
    `config: Any` in 5 stages; duplicated OpenAI-shaped `_extract_usage`;
    three identical compat shims; duplicated pipeline-rebuild in
    Anthropic/LocalClient; FewShotSelectorStage co-located in
    rag_optimizer.py; diversity re-embedding (H7, deferred);
    `compression_attempted` alias (H8, frozen); stringly-coupled stage
    gating (H9, deferred); hard-coded MODEL_COSTS (H10, deferred);
    unkeyed metrics dicts (H11, deferred)
  - **Refactors R1–R6**: `utils/messages.py::get_user_query` (3 copies
    removed); `config: TokenOptConfig | None` + default in all stages;
    `_extract_openai_shape_usage` shared by OpenAI/LocalClient;
    `clients/_compat.py::_CompatShim` (3 forwarders removed);
    `_build_pipeline(routing_rule_filter)` consolidation (Anthropic +
    LocalClient pass model-compatibility filters); `FewShotSelectorStage`
    split to `pipeline/fewshot.py` (exports unchanged)
  - **Deliverable**: `.ai/M13_ARCHITECTURE_REVIEW.md` — hotspot report,
    refactoring summary, internal architecture assessment, technical debt
    report (4-way), self-review (Immediate Recs + ADB-01..10),
    validation summary
  - **Verification**: 167 passed (94% — baseline unchanged), ruff clean,
    mypy green, build + `twine check` PASSED, 6/6 examples vs stub server,
    link check 83 files clean
  - **Docs**: DECISIONS.md Decision 25 (future completion-report format),
    IMPLEMENTATION_ROADMAP M13 completion + deviation notes, README
    untouched (no user-facing change)
- **M14 — Architecture Knowledge Base (2026-08-01)** (session 19;
  docs-only, behavioral freeze)
  - **Deliverable**: `.ai/KNOWLEDGE_BASE/` — 10 files: README index;
    01 System Overview (goals, philosophies, package structure); 02 Request
    Lifecycle (full flow + Mermaid, cache hit/miss/error branches);
    03 Pipeline (order, responsibilities, interactions, fail-open, context
    lifecycle, gating); 04 Provider Layer (abstraction + normalization
    contract spec); 05 Configuration (hierarchy, defaults, overrides,
    validation, extension); 06 Metrics (ownership, propagation,
    routing_reason/precedence, latency, cost); 07 **Architectural
    Contracts C1–C8** (normative); 08 Extension Guide (recipes);
    09 Internal Assessment (Software Factory view + **ADB-11** internal
    architecture contracts, ADB-12 manifest, ADB-13 normalization
    enforcement)
  - **Wiring**: ARCHITECTURE.md pointer section; GOVERNANCE_INDEX
    Knowledge Base registry (owners + normative rule); README pointer line
  - **Validation**: Decision 24 paths + routing_reason fallback + metrics
    vocabulary + config groups cross-checked vs code; 29 md links + 31
    inline paths resolve (2 test-path typos fixed); examples untouched;
    suite 167 unchanged; no runtime code changed
  - **Docs**: IMPLEMENTATION_ROADMAP M14 ✅, TASK_QUEUE, NEXT_STEPS,
    SESSION_STATE, ROADMAP checkbox; README pointer updated

## Open item

- ~~GitHub remote `origin` URL is invalid~~ → **Fixed**: now points to
  `https://github.com/rohit-naik36/TokenOpt.git`; `main` pushed, up to date.

## In progress / not started

- **M15** — release v0.1.0 (⚠ PyPI publish gate at start; audit P0.5:
  pip-audit, Dependabot merges, secret scanning; CI hardening)
- Post-v0.1.0 ADB backlog: High — ADB-03, ADB-11; Medium — ADB-01/02/05/12/13
- Prompt-library live-usage tracking: prompts become "live" after real
  task use or user acceptance (per `.ai/PROMPTS/README.md` maintenance
  rule)
- Full config reference docs pending
- Local client live verification against a real Ollama server
- Merge Dependabot action-upgrade PRs (checkout/setup-python/upload-artifact
  → v7) when convenient — advisory, not blockers

## Verification

- `pytest tests/` → 167 passed (coverage gate enforced, 94%)
- `ruff check tokenopt examples tests` → clean
- `mypy tokenopt` → **green (exit 0)**
- `python -m build` → sdist + wheel OK; **`twine check` PASSED**
- 6 examples validated against stub server (exit 0, truthful)
- **GitHub Actions CI** → full matrix green (verified via GitHub API)
