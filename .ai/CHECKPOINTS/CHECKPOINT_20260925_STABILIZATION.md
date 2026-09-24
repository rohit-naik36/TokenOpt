# Checkpoint: Repository Stabilization & Architecture Hygiene

**Date:** 2026-09-25  
**Branch:** `feature/prototype-v0.1-gateway`  
**Status:** COMPLETE (All 17 stabilization phases passed, 413 tests green, 94% coverage)

---

## 1. Context & Baseline
- CP1–CP7 (Context Analyzer, PreservationMap, Candidate Planner, Transformer, and Validator) merged on `main` at `c1b1086`.
- Prototype v0.1 FastAPI Optimization Gateway implemented on `feature/prototype-v0.1-gateway`.
- Comprehensive stabilization and architecture hygiene executed across all 17 phases prior to beginning Prototype v0.2.

---

## 2. Key Fixes & Architecture Hardening Completed

### Phase 2: Stage Identity & Gating
- Defect resolved: `OptimizationPipeline._should_run_stage` previously checked `stage_name == "rag"`, failing to match `RAGOptimizerStage.name == "rag_optimizer"`.
- Updated to match `stage_name in ("rag", "rag_optimizer")` and `stage_name in ("fewshot", "few_shot")`.
- Verified: `get_prototype_config()` now strictly disables all downstream mutating stages (`ContextSummarizerStage`, `RAGOptimizerStage`, `FewShotSelectorStage`).

### Phase 3: Pipeline Order & Safety Boundary
- Active prototype pipeline: `Analyzer -> Router -> Transformer -> Validator -> Provider`.
- Downstream context mutators remain safely disabled via prototype configuration, establishing `ValidatorStage` as the final gate for context mutations before provider dispatch.

### Phase 4: Token Accounting Separation
- Added `provider_input_tokens` and `provider_output_tokens` to `RequestMetrics`.
- Disentangled local estimation (`original_tokens`, `optimized_tokens` via `tiktoken`) from provider-reported usage (OpenAI `usage.prompt_tokens` / Ollama `prompt_eval_count`).

### Phase 5: Cost Semantics
- Clarified `estimated_cost` as the baseline unoptimized request cost in USD.
- Added `optimized_cost` (post-optimization cost) and `cost_saved` (USD savings) to `RequestMetrics` and `MetricsCollector.get_summary()`.

### Phase 6: Cache Key Hardening
- Updated `CacheStage._make_cache_key` and `_lookup_cache` to incorporate `model` and generation parameters (`temperature`, `max_tokens`, `top_p`, `frequency_penalty`, `presence_penalty`, `stop`).
- Added `metadata` to `CacheEntry` dataclass.
- Both exact-match and semantic lookup now enforce model and generation parameter isolation, preventing cross-model and cross-parameter cache collisions.

### Phase 7: Gateway Contract Lockdown
- Enforced rejection of streaming requests (`stream=true`) with HTTP 400 Bad Request.
- Verified forwarding of advertised parameters (`temperature`, `max_tokens`, `top_p`).
- Sanitized 502 Bad Gateway responses on provider failure.

### Phase 8 & 15: Packaging & Test Coverage Expansion
- Updated `pyproject.toml` to include `fastapi` and `uvicorn` in `[project.optional-dependencies] dev`.
- Updated `.github/workflows/ci.yml` test job to install `".[dev,server]"`.
- Created `tests/test_embeddings.py` covering `SimpleEmbeddingProvider` deterministic exact-match fallback.
- Added test coverage for all 12 target areas; total test suite expanded to **413 tests**, 0 failures, 94% coverage.

### Phase 9, 10, 11, 12, 14: Documentation Alignment
- Clarified repository hierarchy: `tokenopt/` (canonical), `tokenopt-proxy/` and `tokenopt-optimizer/` (legacy reference).
- Cleaned up nonexistent `tokenopt-sdk/` references in `README.md` and `LICENSE`.
- Documented fallback embedding behavior (exact-match hash-based, zero ML dependencies).
- Verified legacy `tokenopt-proxy/tests/` (82 passed).

---

## 3. Verification Metrics

| Check | Result |
|-------|--------|
| `pytest tests/` | **413 passed**, 0 failures, 1 warning (94% coverage) |
| `ruff check tokenopt tests` | **Clean** (0 errors) |
| `mypy tokenopt` | **Clean** (Success: no issues in 29 source files) |
| `tokenopt-proxy/tests/` | **82 passed**, 0 failures |

---

## 4. Next Step
Proceed to **Prototype v0.2 — Evidence Harness** (50 test cases, empirical validation of CP1–CP7 across real-world prompts, automated quality and latency measurement).
