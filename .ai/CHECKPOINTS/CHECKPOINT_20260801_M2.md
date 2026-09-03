# CHECKPOINT_20260801_M2

## Milestone: M2 — Pipeline Stage Tests 1 (router, compressor, summarizer)

## Completed work
- 54 new behavioral-contract unit tests (network-free):
  - `tests/test_router.py` (18) — priority-ordered rules, complexity
    fallback, empty/malformed queries, fail-open rule exceptions,
    determinism, no shared-state mutation
  - `tests/test_compressor.py` (16) — heuristic path, LLMLingua stub +
    fallback, lazy-load gating, edge cases, determinism, no mutation
  - `tests/test_summarizer.py` (13) — threshold gating, custom
    `summarizer_fn`, extractive fallback, system-message reconstruction,
    malformed content, determinism, no mutation
  - `tests/test_pipeline_config.py` (5) — enable/disable gating via
    `OptimizationPipeline`
- **Defect found + fixed (minimal, no API change)**: ContextSummarizerStage
  kept the FIRST 3 non-system messages as "recent" and summarized the NEWEST
  ones (opposite of documented "Keep last 3 messages" intent; latest user
  query could be summarized away). Fixed: recent = `non_system[-3:]`,
  history = `non_system[:-3]`, drop `reversed()`.
- Coverage: router 27% → **100%**; compressor (incl. summarizer) → **100%**;
  suite 62% → **72%** (ad hoc; formal 80% gate in M4).

## Modified files
- `tests/test_router.py` (new)
- `tests/test_compressor.py` (new)
- `tests/test_summarizer.py` (new)
- `tests/test_pipeline_config.py` (new)
- `tokenopt/pipeline/compressor.py` (summarizer recent/history split fix)
- `.ai/` memory: CURRENT_STATE, NEXT_STEPS, SESSION_LOG, SESSION_STATE,
  TASK_QUEUE, IMPLEMENTATION_ROADMAP, this checkpoint

## Commits
- (created after this checkpoint — see `git log --oneline -8`)

## Remaining work
1. **M3** — pipeline stage tests: cache + RAG + few-shot
   (acceptance: new suites green; rag_optimizer/cache coverage ≥ 70%)
2. M4 — integration tests + 80% coverage gate (⚠ HTTP stub dev dep)
3. M5 — CI (GitHub Actions, 3.10–3.12 matrix)
4. M6 — license (⚠ user choice), CHANGELOG, metadata
5. M7 — pip-audit + secret scan + Dependabot (⚠ dev deps)
6. M8 — CONTRIBUTING, Makefile, examples
7. M10–M15 — governance docs, cleanup (⚠), refactor, arch docs, release v0.1.0 (⚠ PyPI optional)

## Blockers
- None. M3 has no approval gate; next approval-gated milestones are M4
  (HTTP stub dev dep) and M6 (license).

## Decisions made
- Summarizer contract ratified by tests: keep system + summary + LAST 3
  non-system messages; summarize older history. Defect fixed to match
  documented intent (no new DECISIONS.md entry — not an architecture change).
- Test isolation approach: stage internals controlled explicitly
  (monkeypatch `_get_llmlingua` / `sys.modules` stub / direct
  `stage._llmlingua`) so suites are deterministic whether or not the
  `llmlingua` optional extra is installed.

## Verification status
- pytest: 77 passed (54 new) ✅
- ruff: clean ✅
- mypy: exit 0 (20 files) ✅
- Coverage: router 100%, compressor 100%, suite 72% (ad hoc) ✅

## Next prompt
"Approved. Begin Milestone 3 from .ai/IMPLEMENTATION_ROADMAP.md: write
network-free unit tests for the cache, RAG optimizer, and few-shot selector
stages (tests/test_cache.py, tests/test_rag_optimizer.py,
tests/test_fewshot.py) per the M3 work list; verify with the .ai/DOD.md
5-gate pipeline; update memory; commit conventional commits; verify
git remote -v (Decision 11); push; create checkpoint; wait for approval
before M4."
