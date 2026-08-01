# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-08-01

### Added

- Drop-in clients for OpenAI (`tokenopt.OpenAI`), Anthropic
  (`tokenopt.Anthropic`), and local model servers (`tokenopt.LocalClient` for
  Ollama, vLLM, llama.cpp, and LM Studio) — same import, same API surface,
  automatic optimization.
- Optimization pipeline with six configurable stages:
  - Model routing (rule-based + complexity scoring)
  - Prompt compression (heuristic; optional LLMLingua)
  - Conversation summarization (extractive fallback, pluggable)
  - Semantic caching (in-memory LRU, optional Redis, TTL)
  - RAG chunk optimization (ranking, threshold, dedup, cap)
  - Few-shot selection (similarity, diversity, random)
- Client factory (`create_client`, `create_client_from_model`,
  `detect_provider`) with auto-detection from model name / base URL.
- Observability: request metrics, aggregated summaries, cost estimation, and
  structured JSON logging; optional `metrics_callback`.
- Configuration via `TokenOptConfig` (per-stage toggles, thresholds, rules).
- MIT License, changelog, and release metadata (authors, classifiers,
  project URLs).
- CI pipeline (GitHub Actions) enforcing the Definition of Done gates:
  ruff, mypy, pytest with ≥80% coverage across Python 3.10–3.12, package
  build + twine check, fresh-venv smoke install, pip-audit, and gitleaks
  secret scan.
- 167 unit + integration tests (offline, deterministic, no network).
- `RequestMetrics.routing_reason` records WHY a request was routed to its
  model: the matched rule name (e.g. `math_tasks`) or
  `complexity-based (low|medium|high)` for the fallback heuristic.
  Additive only — no existing fields changed.
- Routing precedence contract (Decision 24) — `RequestMetrics`
  `routing_precedence` (`explicit | rule | preserve | complexity |
  provider_default`) records the routing decision in machine-readable
  form; `routing_reason` additionally reports `preserved (no rule matched)`
  for unmatched custom rules.
- `docs/UAT.md` — permanent manual acceptance checklist for every release.

### Changed

- **Routing precedence (principle of least surprise, Decision 24)** —
  an explicitly passed `model=` is never overridden by routing; custom
  routing rules that match nothing now **preserve the caller's requested
  model** instead of rewriting it via the complexity fallback (this also
  stops `gpt-*` rewrites on Anthropic/local backends, where they would
  break the API call). Complexity routing still applies when no custom
  rules are configured (including the SDK's built-in default rules), so
  default-config behavior is unchanged. `RoutingRule.builtin` marks the
  SDK's own default rules.
- `examples/` are now value demonstrations: each script leads with a
  "Demonstrates / Expected outcome" header, sends realistic long prompts,
  shows compression OFF vs ON and cache miss → hit comparisons, and prints
  `explain()` lines derived only from the recorded metrics — the printed
  claims can never drift from what the pipeline actually did.
- README example sections describe the demonstrated value per script.
- Per-request metrics now distinguish compression **attempted** (stage ran)
  from **effective** (tokens actually reduced) via `compression_attempted`,
  `compression_effective`, `tokens_saved`, and `reduction_percentage`;
  latency is split into `model_latency_ms` (inference) and
  `pipeline_latency_ms` (TokenOpt overhead). Existing fields unchanged.
- Example scripts print concise, human-readable metrics (model, cache hit,
  compression outcome, tokens, latency split, estimated cost) instead of
  raw structured JSON; JSON logging is unchanged for production use.
- README gained a 5-Minute Quick Start; installation from PyPI
  (`pip install tokenopt`) plus extras table.

### Fixed

- Summarizer kept the oldest messages as "recent" instead of the last 3;
  the latest user query could be summarized away.
- Semantic cache key collision for non-string message content
  (multimodal lists) — content now serialized deterministically.
- RAG dedup compared chunks against misaligned embeddings after
  relevance re-sort.
- Few-shot examples were silently dropped when no system message existed.
- Pipeline stage exceptions propagated and broke requests — stages now
  fail open and record `{stage}_error` metrics.
- The documented drop-in surface `client.chat.completions.create(...)`
  raised `AttributeError` (only `chat.create(...)` worked).
- Anthropic clients routed requests to `gpt-*` models with default config,
  breaking the API call — routing is now scoped to Anthropic models.
- `LocalClient` raised a bare `ModuleNotFoundError` when the optional
  `ollama` package was missing — now a clear error with install guidance.
- mypy gate missed the optional `ollama` import (type gate requires no
  optional extras).

[0.1.0]: https://github.com/rohit-naik36/TokenOpt/releases/tag/v0.1.0
