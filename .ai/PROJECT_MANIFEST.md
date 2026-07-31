# TokenOpt SDK — Project Manifest

_Status: Ratified — 2026-08-01_
_Revision: 1.0_
_This document is the project's constitution. It changes rarely and only with
explicit user approval._

---

## 1. Project Overview

### Project Name

**TokenOpt SDK** (`tokenopt`)

### Vision

Every LLM interaction is automatically optimized — cheaper, faster, and within
context limits — without developers ever changing their code.

### Mission

Provide a drop-in Python SDK that transparently reduces token usage and cost for
OpenAI, Anthropic, and local model deployments through compression, semantic
caching, intelligent routing, and context management — with zero API breakage
and complete observability.

### Business Problem

LLM API costs scale linearly with prompt size and model capability. Teams waste
money on:

- over-long prompts and redundant context,
- expensive models for trivial queries,
- repeated identical requests,
- context-window overflows that fail production requests.

Existing optimization tools require architectural changes or vendor lock-in.
TokenOpt solves this with a drop-in wrapper: `from tokenopt import OpenAI` —
no other code changes required.

### Goals

1. **Drop-in compatibility** — `tokenopt.OpenAI` and `tokenopt.Anthropic` are
   API-compatible with the official SDKs (and locally hosted models too).
2. **Measurable cost reduction** — default pipeline delivers meaningful token
   and cost savings out of the box.
3. **Transparent optimization** — every optimization is logged and attributable;
   nothing is hidden from the developer.
4. **Zero heavy dependencies by default** — optional capabilities via extras.
5. **Enterprise-grade quality** — documented, tested, linted, versioned, and
   governed like a production open-source project.

### Non-Goals

- Replacing the underlying provider SDKs (we wrap, never reimplement).
- Providing model hosting, serving, or fine-tuning infrastructure.
- Managing API keys or secret storage (delegated to the user/environment).
- Multi-tenancy, RBAC, or org-level admin features (personal/small-team target).
- Guaranteeing identical output quality on every optimization (approximation is
  accepted where metrics prove the trade-off).
- Async-native APIs (async support is a future goal, not a v0.x goal).

### Success Criteria

| Criterion | Target |
|-----------|--------|
| Drop-in compatibility | 100% of common `chat.completions`/`messages` usage works unchanged |
| Average token reduction (compression on) | ≥ 30% on long-prompt workloads |
| Cache hit rate (repeated workloads) | ≥ 50% on duplicate/similar prompts |
| Cost estimation accuracy | Within ±20% of provider billing for known models |
| Test coverage | ≥ 80% line coverage for core modules |
| Time-to-integrate | < 5 minutes for a new user |

---

## 2. Product Definition

### Target Users

- Individual developers and small teams using OpenAI, Anthropic, or local models
  (Ollama, vLLM, llama.cpp).
- Builders of RAG applications and multi-turn agents with large contexts.
- Developers migrating between providers who want a single optimized API surface.

### Primary Use Cases

1. Drop-in replacement for `openai.OpenAI` / `anthropic.Anthropic` with
   automatic compression and caching.
2. Multi-model routing — cheap models for simple queries, strong models for
   complex reasoning.
3. Local-model development (Ollama/vLLM/llama.cpp) with the same optimization
   pipeline and metrics.
4. RAG and few-shot workloads where context pruning and example selection cut
   tokens without cutting quality.
5. Cost/latency observability via built-in metrics and structured logs.

### MVP Scope (v1.0)

- OpenAI, Anthropic, and local (Ollama + OpenAI-compatible) clients
- Optimization pipeline: router, compressor, summarizer, semantic cache,
  RAG optimizer, few-shot selector — all configurable
- Metrics collector + cost estimation
- Client factory with provider auto-detection
- Solid unit + integration test suite, docs, packaging

### Future Scope (v1.x → v2.x)

- Streaming passthrough for all providers
- Cache persistence (file-backed) and smarter eviction
- Pluggable summarization models
- Real LLMLingua integration
- Router with live cost/latency feedback
- Prometheus exporter and dashboards
- Prompt versioning registry

### Out of Scope

- Web UI as a product requirement (experimentation UI is post-v3)
- Enterprise auth/tenancy/SSO
- Non-Python SDKs
- Model training or serving

---

## 3. Technical Vision

### High-level Architecture

```
User code ──► Client wrapper (OpenAI/Anthropic/Local)
                │
                ▼
        OptimizationPipeline (sequential stages)
        router → compressor → summarizer → cache → RAG → few-shot
                │
                ▼
        Provider API (openai / anthropic / ollama / OpenAI-compatible)
                │
                ▼
        Response ──► cache store ──► metrics collector ──► structured logs
```

See `.ai/ARCHITECTURE.md` for the full reference.

### Technology Stack

- **Language:** Python (≥ 3.10)
- **Core deps:** `openai`, `anthropic`, `tiktoken`, `pydantic`, `pydantic-settings`, `numpy`
- **Optional extras:** `redis` (cache), `sentence-transformers` (semantic),
  `llmlingua` (compression), `ollama` (local)
- **Dev tooling:** `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `mypy`
- **Packaging:** `setuptools` via `pyproject.toml`

### Supported Providers

| Provider | Interface | Status |
|----------|-----------|--------|
| OpenAI | `tokenopt.OpenAI` (drop-in) | v0.1 |
| Anthropic | `tokenopt.Anthropic` (drop-in) | v0.1 |
| Ollama | `tokenopt.LocalClient` (native, auto-detect) | v0.1 |
| vLLM / llama.cpp / LM Studio | `tokenopt.LocalClient` (OpenAI-compatible) | v0.1 |

### Supported Python Versions

- **Target:** 3.10, 3.11, 3.12 (CI matrix to be added)
- **Minimum:** 3.10 (declared in `pyproject.toml`)

### Design Principles

1. **Drop-in first** — the wrapped API surface is sacred; never break it.
2. **Composable pipeline** — stages are independent, configurable, swappable.
3. **Fail open** — if an optimization stage errors, the request still succeeds
   (optimization is best-effort; correctness is not).
4. **No heavy defaults** — ML and external services are optional extras.
5. **Observability by default** — every request produces metrics and logs.
6. **Backend normalization** — normalize provider responses to one shape so the
   pipeline is provider-agnostic.
7. **Explicit over magic** — routing and compression decisions are visible and
   configurable, never opaque.

---

## 4. Engineering Standards

### Coding Standards

- Python ≥ 3.10; type hints required on all public and private functions.
- Lint: `ruff` with `E, F, I, UP, W` rules, line length 100, `py310` target —
  zero findings required before commit.
- Types: `mypy` strict-mode progress; no `Any` in public signatures where
  avoidable.
- No comments unless they explain *why*; code must be self-documenting.
- Imports sorted (isort via ruff); absolute imports preferred.

### Documentation Standards

- Every module has a docstring; every public class/function has a docstring.
- `README.md` is the user entry point.
- `.ai/PROJECT_MANIFEST.md` is the constitution — changes only with user approval.
- `.ai/` docs are the source of truth for state, decisions, roadmap, and handoff.
- Update documentation in the same commit as the code it describes.

### Testing Standards

- Tests live in `tests/`, one module per unit under test.
- Unit tests must not hit the network — providers are stubbed/faked.
- New features require tests before they count as done (see Definition of Done).
- Coverage target: ≥ 80% lines for `tokenopt/` (measured by `pytest-cov`).
- Test naming: `test_<behavior>` descriptive of intent.

### Logging Standards

- Structured JSON logging via `tokenopt.observability.logger.StructuredLogger`.
- Log context: request id, model, token counts, latency, applied optimizations.
- Sensitive data (API keys, full prompts by default, PII) must never be logged.
- Log levels: DEBUG (development), INFO (request lifecycle), WARNING/ERROR
  (failures). Metrics-callback failures are swallowed, never fatal.

### Error Handling Standards

- Provider errors propagate to the caller (drop-in behavior preserved).
- Optimization-stage errors are caught and downgraded (fail-open principle).
- Configuration errors (`TokenOptConfig` validation) raise early at init.
- Unknown model names fall back to a safe default tokenizer (`cl100k_base`).

### Security Standards

- Never log, print, or persist API keys or secrets.
- Never commit secrets; `.env` and credential files are gitignored.
- No secret handling in the SDK — keys come from the caller/environment.
- Dependabot-style dependency hygiene: review pinned ranges on release.
- Remote URLs are never modified or guessed automatically (Decision 11) —
  pushes only to a user-verified remote.

---

## 5. Git Strategy

### Branching Strategy

- `main` is the only permanent branch; it must always be green (tests + lint pass).
- Feature work: short-lived branches (`feat/<slug>`) merged via PR/rebase onto
  `main`.
- Hotfixes: `fix/<slug>` directly to `main` when a release needs immediate repair.
- No long-lived integration branches.

### Commit Message Convention

```
<type>: <summary>

Examples: feat:, fix:, refactor:, docs:, test:, chore:
```

- One logical change per commit; small commits, never giant ones.
- Imperative mood, ≤ 72 characters for the summary line.
- A feature is committed only when implementation, tests, lint, and docs are done.

### Release Strategy

- Tag-based releases on `main`: `vX.Y.Z`.
- A release candidate (`vX.Y.Z-rcN`) may precede a final tag.
- Changelog entries recorded in release notes (GitHub Releases when available;
  `CHANGELOG.md` otherwise).
- Post-tag verification: clean checkout, install, test suite, import smoke test.

### Versioning Strategy

- Semantic Versioning (`MAJOR.MINOR.PATCH`) per https://semver.org.
- `MAJOR` — breaking API changes (require user approval per governance).
- `MINOR` — backward-compatible features.
- `PATCH` — backward-compatible fixes.
- v0.x: `MINOR` bumps may contain breaking changes with explicit notice.

---

## 6. Development Workflow

The expected lifecycle for every feature or fix:

```
Idea
 │
 ▼
Requirements ──► clarify scope, success criteria (Definition of Done)
 │
 ▼
Architecture ──► design; update .ai/ARCHITECTURE.md and DECISIONS.md if changed
 │
 ▼
Implementation ──► code the change (small, focused)
 │
 ▼
Testing ──► unit + integration tests; pytest green
 │
 ▼
Documentation ──► README/docstrings/.ai docs updated with the change
 │
 ▼
Review ──► self-review: ruff, mypy, diff review against standards
 │
 ▼
Git Commit ──► small logical commit (conventional message)
 │
 ▼
GitHub Push ──► verify remote (Decision 11), push branch/PR
 │
 ▼
Checkpoint ──► .ai/CHECKPOINTS/CHECKPOINT_YYYYMMDD_HHMM.md on milestones
 │
 ▼
Release ──► tag vX.Y.Z when releasable
```

---

## 7. Definition of Done

A feature is considered complete **only** when all of the following are true:

- [ ] Implementation completed (code written, self-reviewed)
- [ ] Tests pass (`pytest tests/`)
- [ ] Lint passes (`ruff check tokenopt tests`)
- [ ] Documentation updated (docstrings/README as applicable)
- [ ] Project memory updated (`.ai/CURRENT_STATE.md`, `.ai/NEXT_STEPS.md`,
      `.ai/SESSION_LOG.md` as applicable)
- [ ] Checkpoint created for the milestone (`.ai/CHECKPOINTS/`)
- [ ] Committed with a conventional message
- [ ] Pushed to GitHub (remote verified first)

---

## 8. AI Agent Rules

Every AI agent working on this repository **must**:

- [ ] Read `AGENTS.md` (root) if present
- [ ] Read `.ai/PROJECT_MANIFEST.md` before any work
- [ ] Read everything inside `.ai/` (state, decisions, roadmap, logs, checkpoints)
- [ ] Follow all recorded architecture decisions (`.ai/DECISIONS.md`)
- [ ] Never overwrite or delete checkpoints — always create new ones
- [ ] Ask the user before breaking or changing public APIs
- [ ] Commit frequently in small logical commits
- [ ] Push only after milestones, and only after verifying the remote
      (Decision 11) — never modify or guess the remote URL
- [ ] Ask for approval before: architecture changes, file deletions,
      dependency changes, API changes, schema changes

---

## 9. Repository Conventions

### Folder Structure

```
<repo root>/
├── .ai/               # Project memory (state, decisions, roadmap, checkpoints)
│   └── CHECKPOINTS/   # One file per milestone; append-only
├── tokenopt/          # SDK package
│   ├── clients/       # Provider wrappers
│   ├── pipeline/      # Optimization stages
│   ├── observability/ # Metrics + logging
│   └── utils/         # Token counting, embeddings
├── tests/             # Unit and integration tests
├── pyproject.toml     # Packaging, tool config
└── README.md          # User documentation
```

### Naming Conventions

- Files/dirs: `snake_case.py`
- Classes: `PascalCase`; functions/methods/variables: `snake_case`
- Private helpers: leading underscore (`_helper`)
- Pipeline stages: noun-suffixed (`CompressorStage`, `CacheStage`) with a
  lowercase `name` attribute
- Test files: `test_<module>.py`; test functions: `test_<behavior>`

### Documentation Conventions

- All docs in Markdown (CommonMark).
- `.ai/` files have a `_Last updated: YYYY-MM-DD_` line.
- Checkpoints: `CHECKPOINT_YYYYMMDD_HHMM.md`, never overwritten.
- Decisions: append-only table in `.ai/DECISIONS.md`.

### Configuration Conventions

- Single source of truth: `tokenopt/config.py` → `TokenOptConfig` dataclass.
- All behavior is config-driven via `TokenOptConfig`; no hidden flags.
- Optional capabilities behind extras: `cache`, `semantic`, `compression`,
  `local`, `dev`, `all`.
- Config validated at construction; invalid values raise `ValueError`.

### Testing Conventions

- `pytest` with `asyncio_mode = "auto"`.
- Unit tests: no network; provider calls faked via subclassing or mocks.
- Test the pipeline through the client (integration) and stages in isolation.
- Never assert on timing-sensitive values except broad bounds.

---

## 10. Release Process

1. **Freeze scope** — all Definition-of-Done items complete on `main`.
2. **Version bump** — `MAJOR.MINOR.PATCH` per SemVer; update `__version__`
   in `tokenopt/__init__.py` and `pyproject.toml`.
3. **Changelog** — record changes under the new version.
4. **Verification gate** — on a clean checkout:
   - `pytest tests/` (all green)
   - `ruff check tokenopt tests` (clean)
   - `pip install .` succeeds and `import tokenopt` reports the version
5. **Tag** — `git tag vX.Y.Z` on `main`; push tag (remote verified).
6. **Release notes** — publish via GitHub Releases (or `CHANGELOG.md` if
   unavailable): summary, breaking changes, new features, fixes.
7. **Post-release** — update `.ai/CURRENT_STATE.md` with the released version;
   checkpoint the release.

---

## 11. Long-Term Vision

### After v1.0 — "Production baseline"

- Stable drop-in API; breaking changes only with deprecation notices.
- ≥ 80% test coverage; CI on GitHub Actions (test matrix 3.10–3.12, lint, mypy).
- Streaming, cache persistence, pluggable summarizer, LLMLingua integration.
- Published to PyPI; installable via `pip install tokenopt`.
- Live cost/latency tracking per model and dynamic routing.

### After v2.0 — "Optimization platform"

- Multi-provider routing with real-time cost/latency feedback and budget caps.
- Prometheus exporter + dashboards; per-project/per-model cost analytics.
- Prompt versioning registry and A/B testing framework built on the pipeline.
- Team config sharing (config-as-code files).
- Async-native clients.

### After v3.0 — "Self-optimizing SDK"

- Autonomous optimization: the SDK learns routing/compression policies from
  usage telemetry (opt-in).
- Web UI for experimentation and policy management.
- Integration with the broader LLM tooling ecosystem (agents, RAG frameworks,
  evaluation harnesses).
- Enterprise features: audit trails, policy enforcement, SSO, compliance hooks.

---

_End of manifest. Amendments require explicit user approval and a revision bump
of the `Revision:` line above._
