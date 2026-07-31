# Next Steps

_Last updated: 2026-08-01 (M1 complete — verification gates green, DoD ratified)_

## M1 done — M2 is next

M1 (Verification Gates) is complete: mypy gate green (numpy pin + 37 typing
fixes + latent summarizer bug), `.ai/DOD.md` ratified, gates documented in
AGENTS.md/README/standards. **M2 awaits go-ahead.**

1. **M2** — Pipeline stage tests: router + compressor + summarizer
   (acceptance: new suites green; router/compressor coverage > 70%)
2. **M3** — Pipeline stage tests: cache + RAG + few-shot
3. **M4** — Integration tests (mock servers) + formal 80% coverage gate
   (⚠ new dev dep)
4. **M5** — CI pipeline (GitHub Actions, Python 3.10–3.12 matrix)
5. **M6** — Release metadata: license (⚠ user choice), classifiers, CHANGELOG,
   `python -m build` verification
6. **M7** — Security hardening: pip-audit + secret scanning + Dependabot
   (⚠ new dev deps)
7. **M8** — Onboarding: CONTRIBUTING.md, Makefile, examples/
8. **M10** — Extend `.ai/WORKFLOWS/` + `.ai/ROLES/` to full sets (audit §5)
9. **M11** — `.ai/PROMPTS/` (9 prompts; optional)
10. **M12** — Structure cleanup: artifact dirs (⚠ deletion approval),
    archive SESSION_BACKUP.md, GitHub templates
11. **M13** — Maintainability refactor: response helpers, data-driven MODEL_COSTS
12. **M14** — Architecture docs polish: Mermaid diagrams, normalization spec,
    extension guide
13. **M15** — Release v0.1.0: tag, release notes, optional PyPI (⚠ publish)

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
