# TokenOpt SDK — Current State

_Last updated: 2026-08-01 (M1 + M2 complete — Verification Gates + Pipeline Stage Tests 1)_

## Status: Phase 0 + Phase 1 + M1 + M2 complete; next is M3 (cache/RAG/few-shot tests)

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

## Open item

- ~~GitHub remote `origin` URL is invalid~~ → **Fixed**: now points to
  `https://github.com/rohit-naik36/TokenOpt.git`; `main` pushed, up to date.

## In progress / not started

- **M3** — pipeline stage tests: cache + RAG + few-shot (next)
- Integration tests + coverage gate (M4), CI (M5), release metadata (M6),
  security scans (M7), DX (M8), governance docs extension (M10/M11 pending),
  cleanup (M12), refactor (M13), arch docs (M14), release v0.1.0 (M15)
- README usage examples complete; full config reference pending
- Local client live verification against a real Ollama server

## Verification

- `pytest tests/` → 77 passed
- `ruff check tokenopt tests` → clean
- `mypy tokenopt` → **green (exit 0)**
- Coverage: router 100%, compressor 100%, suite 72% (ad hoc; formal 80% gate in M4)
