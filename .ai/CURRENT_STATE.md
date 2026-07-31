# TokenOpt SDK — Current State

_Last updated: 2026-08-01_

## Status: Phase 1 complete, Phase 2 started (v0.1.0)

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
- **Packaging** — `pip install -e .` verified, README exists
- **Lint** — `ruff check tokenopt tests` fully clean (fixed 64+ findings incl.
  one latent bug: missing import in `pipeline/compressor.py`)

## Open item

- ~~GitHub remote `origin` URL is invalid~~ → **Fixed**: now points to
  `https://github.com/rohit-naik36/TokenOpt.git`; `main` pushed, up to date.

## In progress / not started

- Root `AGENTS.md` (referenced by manifest §8) — not yet created
- Pipeline stage unit tests (compressor/cache/router/RAG/few-shot individually)
- Integration tests (mock API servers)
- README usage examples complete; full config reference pending
- Local client live verification against a real Ollama server
- Phase 2 enhancements (see NEXT_STEPS.md)

## Verification

- `pytest tests/` → 23 passed
- `ruff check tokenopt tests` → clean
- `pip install -e .` → success; `import tokenopt` → v0.1.0
