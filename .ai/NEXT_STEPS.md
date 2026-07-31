# Next Steps

_Last updated: 2026-08-01 (M3 complete — pipeline stage tests 2 green)_

## M3 done — M4 is next (⚠ approval gate)

M3 (Pipeline Stage Tests 2) is complete: 53 new behavioral-contract tests
(cache 18, RAG 15, few-shot 13, pipeline gating +7); four defects found and
fixed (cache key collision for non-string content, RAG dedup embedding
misalignment, few-shot injection without system message, pipeline fail-open);
cache 96% / rag_optimizer 98% coverage; suite 130 tests green, ruff clean,
mypy exit 0. **M4 needs approval** (⚠ new dev dependency: HTTP stub library).

1. **M4** — Integration tests (mock servers) + formal 80% coverage gate
   (⚠ new dev dep — approval required before start)
2. **M5** — CI pipeline (GitHub Actions, Python 3.10–3.12 matrix)
3. **M6** — Release metadata: license (⚠ user choice), classifiers, CHANGELOG,
   `python -m build` verification
4. **M7** — Security hardening: pip-audit + secret scanning + Dependabot
   (⚠ new dev deps)
5. **M8** — Onboarding: CONTRIBUTING.md, Makefile, examples/
6. **M10** — Extend `.ai/WORKFLOWS/` + `.ai/ROLES/` to full sets (audit §5)
7. **M11** — `.ai/PROMPTS/` (9 prompts; optional)
8. **M12** — Structure cleanup: artifact dirs (⚠ deletion approval),
   archive SESSION_BACKUP.md, GitHub templates
9. **M13** — Maintainability refactor: response helpers, data-driven MODEL_COSTS
10. **M14** — Architecture docs polish: Mermaid diagrams, normalization spec,
    extension guide
11. **M15** — Release v0.1.0: tag, release notes, optional PyPI (⚠ publish)

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
