# TokenOpt SDK — Current State

_Last updated: 2026-08-01 (M1–M6 complete — through release metadata)_

## Status: Phase 0 + Phase 1 + M1–M6 complete; next is M7 (security hardening)

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

## Open item

- ~~GitHub remote `origin` URL is invalid~~ → **Fixed**: now points to
  `https://github.com/rohit-naik36/TokenOpt.git`; `main` pushed, up to date.

## In progress / not started

- **M7** — Security hardening: pip-audit + secret scanning + Dependabot
  (⚠ new dev deps — needs approval)
- DX (M8), governance
  docs extension (M10/M11 pending), cleanup (M12), refactor (M13), arch docs
  (M14), release v0.1.0 (M15)
- README usage examples complete; full config reference pending
- Local client live verification against a real Ollama server
- Personalize author name before PyPI publish (currently GitHub handle,
  per Decision 17)
- Known follow-up (needs decision): `RouterStage` complexity fallback still
  rewrites models when custom rules exist but none match — shared by
  LocalClient/Anthropic custom-rule paths; deferred to avoid changing OpenAI
  routing behavior without approval

## Verification

- `pytest tests/` → 150 passed (coverage gate enforced, 94%)
- `ruff check tokenopt tests` → clean
- `mypy tokenopt` → **green (exit 0)**
- `python -m build` → sdist + wheel OK; **`twine check` PASSED**
- Fresh-venv wheel install + import + metadata check → OK (v0.1.0, MIT)
- **GitHub Actions CI** → full matrix green (verified via GitHub API)
