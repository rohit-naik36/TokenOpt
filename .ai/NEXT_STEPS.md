# Next Steps

_Last updated: 2026-08-01_

## Approved roadmap — awaiting M1 go-ahead

The implementation roadmap (`.ai/IMPLEMENTATION_ROADMAP.md`) is approved with
Phase 0 (AI Engineering Foundation, M0.1–M0.3) completed. **M1 is next and
awaits explicit approval to begin.**

1. **M1** — Fix the mypy/numpy type gate (pin `numpy` or mypy override;
   ⚠ dependency change approval), make `mypy tokenopt` green
2. **M2** — Pipeline stage tests: router + compressor + summarizer
3. **M3** — Pipeline stage tests: cache + RAG + few-shot
4. **M4** — Integration tests (mock servers) + formal 80% coverage gate
   (⚠ new dev dep)
5. **M5** — CI pipeline (GitHub Actions, Python 3.10–3.12 matrix)
6. **M6** — Release metadata: license (⚠ user choice), classifiers, CHANGELOG,
   `python -m build` verification
7. **M7** — Security hardening: pip-audit + secret scanning + Dependabot
   (⚠ new dev deps)
8. **M8** — Onboarding: CONTRIBUTING.md, Makefile, examples/
9. **M9** — Ratify `.ai/STANDARDS/` — **done in Phase 0** (superseded)
10. **M10** — Extend `.ai/WORKFLOWS/` + `.ai/ROLES/` to full sets (audit §5)
11. **M11** — `.ai/PROMPTS/` (9 prompts; optional)
12. **M12** — Structure cleanup: artifact dirs (⚠ deletion approval),
    archive SESSION_BACKUP.md, GitHub templates
13. **M13** — Maintainability refactor: response helpers, data-driven MODEL_COSTS
14. **M14** — Architecture docs polish: Mermaid diagrams, normalization spec,
    extension guide
15. **M15** — Release v0.1.0: tag, release notes, optional PyPI (⚠ publish)

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
