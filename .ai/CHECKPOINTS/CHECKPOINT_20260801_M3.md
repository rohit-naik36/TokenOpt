# CHECKPOINT_20260801_M3

## Milestone: M3 — Pipeline Stage Tests 2 (cache, RAG, few-shot)

## Completed work
- 53 new behavioral-contract unit tests (network-free):
  - `tests/test_cache.py` (18) — hit/miss/roundtrip, TTL expiry, LRU
    eviction, semantic threshold hit/miss, model mismatch, Redis roundtrip +
    failure fail-open (fakes), clear/stats, non-string content, determinism,
    no mutation
  - `tests/test_rag_optimizer.py` (15) — extraction (context:/retrieved:/
    rag_chunks key), ranking/threshold/cap, dedup incl. reorder-alignment
    defect, no-op paths, malformed content, determinism, no mutation
  - `tests/test_fewshot.py` (13) — similarity/diversity/random strategies,
    caps, injection format incl. no-system prepend defect, determinism
  - `tests/test_pipeline_config.py` (+7) — cache gating, RAG/few-shot
    always-on, pipeline fail-open
- **4 defects found + fixed (minimal, no API change)**:
  1. Cache key collision for non-string content (`json.dumps(sort_keys=True)`
     normalization in `_make_cache_key`/`_messages_to_text`)
  2. RAG dedup misaligned embeddings after re-sort (embeddings carried
     through sort in scored tuples)
  3. Few-shot nothing injected without system message (examples prepended)
  4. Pipeline stage exceptions broke requests — `OptimizationPipeline.run`
     fails open per stage, records `{stage}_error` metric
- Coverage: cache 68% → **96%**; rag_optimizer 24% → **98%**; suite 72% →
  **89%** (ad hoc; formal gate M4).

## Modified files
- `tests/test_cache.py`, `tests/test_rag_optimizer.py`, `tests/test_fewshot.py` (new)
- `tests/test_pipeline_config.py` (gating + fail-open additions)
- `tokenopt/pipeline/cache.py` (key/text normalization fix)
- `tokenopt/pipeline/rag_optimizer.py` (dedup embeddings + few-shot prepend fixes)
- `tokenopt/pipeline/base.py` (fail-open in `OptimizationPipeline.run`)
- `.ai/` memory: CURRENT_STATE, NEXT_STEPS, SESSION_LOG, SESSION_STATE,
  TASK_QUEUE, IMPLEMENTATION_ROADMAP, this checkpoint

## Commits
- (created after this checkpoint — see `git log --oneline -8`)

## Remaining work
1. **M4** — integration tests (mock servers) + formal 80% coverage gate
   (**⚠ approval needed: new HTTP stub dev dep**)
2. M5 — CI (GitHub Actions, 3.10–3.12 matrix)
3. M6 — license (⚠ user choice), CHANGELOG, metadata
4. M7 — pip-audit + secret scan + Dependabot (⚠ dev deps)
5. M8 — CONTRIBUTING, Makefile, examples
6. M10–M15 — governance docs, cleanup (⚠), refactor, arch docs, release v0.1.0 (⚠ PyPI optional)

## Blockers
- None for M3. **M4 has an approval gate** (new dev/test dependency: HTTP
  stub library). M6 (license) and M15 (PyPI) later.

## Decisions made
- Fail-open is now enforced at the pipeline level: stage exceptions are
  caught per stage and recorded as `{stage}_error` metrics; subsequent stages
  still run. Aligns with manifest design principle 3 (no DECISIONS.md entry
  needed — restoring documented behavior).
- Test isolation: scripted embedding providers (deterministic similarity
  tables) for cache/RAG/few-shot; fake Redis clients; monkeypatched
  `random.sample` for the random strategy.
- Non-string message content now participates in cache keys and embedding
  text via stable JSON serialization (sort_keys).

## Verification status
- pytest: 130 passed (53 new) ✅
- ruff: clean ✅
- mypy: exit 0 (20 files) ✅
- Coverage: cache 96%, rag_optimizer 98%, suite 89% (ad hoc) ✅

## Next prompt
"Approved. Begin Milestone 4 from .ai/IMPLEMENTATION_ROADMAP.md: integration
tests (tests/integration/) with a mocked HTTP server library (user-approved
dev dep, e.g. responses or pytest-httpx) covering the full drop-in flow
(optimize → call → cache store → metrics), cache-hit short-circuit (no second
network call), provider-error path (metrics recorded, re-raise, fail-open of
stages), and factory + LocalClient against OpenAI-compatible/Ollama-shaped
servers; configure [tool.coverage] fail-under 80% for tokenopt/; verify with
the .ai/DOD.md 5-gate pipeline; update memory; commit conventional commits;
verify git remote -v (Decision 11); push; create checkpoint; wait for
approval before M5."
