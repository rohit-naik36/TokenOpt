# Next Steps

_Last updated: 2026-08-01 (M2 complete — pipeline stage tests 1 green)_

## M2 done — M3 is next

M2 (Pipeline Stage Tests 1) is complete: 54 new behavioral-contract tests
(router 18, compressor 16, summarizer 13, pipeline gating 5); one defect found
and fixed (summarizer kept oldest messages as "recent"); router and compressor
coverage at 100%; suite 77 tests green, ruff clean, mypy exit 0. **M3 awaits
go-ahead.**

1. **M3** — Pipeline stage tests: cache + RAG + few-shot
   (acceptance: new suites green; rag_optimizer/cache coverage ≥ 70%)
2. **M4** — Integration tests (mock servers) + formal 80% coverage gate
   (⚠ new dev dep)
3. **M5** — CI pipeline (GitHub Actions, Python 3.10–3.12 matrix)
4. **M6** — Release metadata: license (⚠ user choice), classifiers, CHANGELOG,
   `python -m build` verification
5. **M7** — Security hardening: pip-audit + secret scanning + Dependabot
   (⚠ new dev deps)
6. **M8** — Onboarding: CONTRIBUTING.md, Makefile, examples/
7. **M10** — Extend `.ai/WORKFLOWS/` + `.ai/ROLES/` to full sets (audit §5)
8. **M11** — `.ai/PROMPTS/` (9 prompts; optional)
9. **M12** — Structure cleanup: artifact dirs (⚠ deletion approval),
   archive SESSION_BACKUP.md, GitHub templates
10. **M13** — Maintainability refactor: response helpers, data-driven MODEL_COSTS
11. **M14** — Architecture docs polish: Mermaid diagrams, normalization spec,
    extension guide
12. **M15** — Release v0.1.0: tag, release notes, optional PyPI (⚠ publish)

## Short term (Phase 2, after M7 per roadmap)

- **Router** — per-model cost/latency tracking, dynamic routing
- **Cache** — persistence (Redis done, add file-backed), better eviction
- **Summarizer** — pluggable summarization model
- **Compressor** — real LLMLingua integration + improved heuristics
- **Local client** — streaming support (`stream=True` passthrough is stubbed
  but responses are not streamed through base client)
- **Observability** — Prometheus exporter option, cost tracking per project/model

## Longer term (post-v1)

- Prompt versioning/registry, A/B testing framework, team config sharing,
  web UI for experimentation
