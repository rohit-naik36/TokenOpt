# Roadmap

_Last updated: 2026-08-01_

## Phase 0 — AI Engineering Foundation (DONE)
- [x] M0.1 `.ai/STANDARDS/` (8 normative standards)
- [x] M0.2 `.ai/WORKFLOWS/` (14 runbooks after M10 expansion)
- [x] M0.3 `.ai/ROLES/` (11 role definitions after M10 expansion)
- [x] Manifest + AGENTS.md reference updates
- [x] Session management policy (Decision 12): SESSION_STATE.md + TASK_QUEUE.md

## Phase 1 — Core infrastructure (DONE)
- [x] Project setup (pyproject, extras)
- [x] Config, token counting, embeddings
- [x] Pipeline framework + all stages (compressor, summarizer, cache, router, RAG, few-shot)
- [x] Observability (metrics, logging, cost estimation)
- [x] OpenAI / Anthropic / Local client wrappers
- [x] Client factory + package exports
- [x] Baseline unit tests (23)

## Phase 2 — Hardening & enhancements (NEXT)
- [x] M1 fix mypy/numpy type gate (⚠ approval: numpy pin)
- [x] M2/M3 pipeline stage unit tests
- [x] M4 integration tests + coverage gate (94% ≥ 80% enforced by pytest)
- [x] M5 CI pipeline (green on GitHub: lint / test 3.10–3.12 / package+smoke)
- [x] M6 release metadata (⚠ license — MIT chosen; changelog, classifiers, URLs, twine check PASSED)
- [x] M7 security scans (pip-audit + gitleaks + Dependabot + SECURITY.md)
- [x] M8 onboarding (CONTRIBUTING, Makefile, examples)
- [x] M8.2 value demonstrations (routing_reason, examples as showcases)
- [x] M10 governance expansion (14 workflows, 11 roles, index + review)
- [x] M11 prompt library (10 prompts, grouped by purpose)
- [x] M12 cleanup (⚠ deletions), M13 refactor, M14 arch docs (KB: `.ai/KNOWLEDGE_BASE/`)
- [ ] M15 release v0.1.0 (⚠ optional PyPI publish)
- [ ] Pipeline stage unit tests
- [ ] Integration tests (mock servers)
- [ ] README + docs
- [ ] Router: cost/latency tracking, dynamic routing
- [ ] Cache: file persistence, better eviction
- [ ] Summarizer: pluggable summarization model
- [ ] Compressor: real LLMLingua integration
- [ ] Local client: streaming
- [ ] Prometheus exporter option

## Post-v1 — Advanced
- [ ] Prompt versioning/registry
- [ ] A/B testing framework
- [ ] Team config sharing
- [ ] Web UI for experimentation
