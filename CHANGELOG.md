# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Per-request metrics now distinguish compression **attempted** (stage ran)
  from **effective** (tokens actually reduced) via `compression_attempted`,
  `compression_effective`, `tokens_saved`, and `reduction_percentage`;
  latency is split into `model_latency_ms` (inference) and
  `pipeline_latency_ms` (TokenOpt overhead). Existing fields unchanged.
- Example scripts print concise, human-readable metrics (model, cache hit,
  compression outcome, tokens, latency split, estimated cost) instead of
  raw structured JSON; JSON logging is unchanged for production use.
- README gained a 5-Minute Quick Start and `docs/UAT.md` became the
  permanent manual acceptance checklist.

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
  build, and fresh-venv smoke install.
- 150 unit + integration tests (offline, deterministic, no network).

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

[Unreleased]: https://github.com/rohit-naik36/TokenOpt/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/rohit-naik36/TokenOpt/releases/tag/v0.1.0
