# TokenOpt SDK — Current State

_Last updated: 2026-08-01 (M1–M8 + UAT refinements + M8.2 + M10 complete; next is M11)_

## Status: Phase 0 + Phase 1 + M1–M8 + Post-M8 UAT refinements + M8.2 + M10 complete

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

## Open item

- ~~GitHub remote `origin` URL is invalid~~ → **Fixed**: now points to
  `https://github.com/rohit-naik36/TokenOpt.git`; `main` pushed, up to date.

## In progress / not started

- **M11** — `.ai/PROMPTS/` (optional; depends on M10)
- M12 cleanup (⚠), M13 refactor, M14 arch docs,
  M15 release v0.1.0 (⚠ PyPI optional)
- Full config reference docs pending
- Local client live verification against a real Ollama server
- Merge Dependabot action-upgrade PRs (checkout/setup-python/upload-artifact
  → v7) when convenient — advisory, not blockers
- Known follow-up (needs decision): `RouterStage` complexity fallback still
  rewrites models when custom rules exist but none match — shared by
  LocalClient/Anthropic custom-rule paths; deferred to avoid changing OpenAI
  routing behavior without approval

## Verification

- `pytest tests/` → 158 passed (coverage gate enforced, 94%)
- `ruff check tokenopt examples tests` → clean
- `mypy tokenopt` → **green (exit 0)**
- `python -m build` → sdist + wheel OK; **`twine check` PASSED**
- Fresh-venv wheel install + import + metadata check → OK (v0.1.0, MIT)
- 6 examples validated in clean venv against stub server (exit 0, truthful)
- **GitHub Actions CI** → full matrix green (verified via GitHub API)
