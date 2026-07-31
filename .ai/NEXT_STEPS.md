# Next Steps

_Last updated: 2026-08-01 (M4 complete — integration tests + coverage gate green)_

## M4 done — M5 is next

M4 (Integration Tests & Coverage Gate) is complete: `tests/integration/` with
19 tests over `httpx.MockTransport` (zero new deps — `http_client=` injection,
Decision 15); `INTEGRATION_TEST_STRATEGY.md` added; `[tool.coverage]
fail_under = 80` + `--cov` in pytest `addopts`; two genuine integration defects
fixed (drop-in `chat.completions.create` surface restored — Decision 14;
Anthropic router scoped to claude models — Decision 13); suite **149 green,
coverage 94%**, ruff clean, mypy exit 0. **M5 has no approval gate.**

1. **M5** — CI pipeline (GitHub Actions, Python 3.10–3.12 matrix)
2. **M6** — Release metadata: license (⚠ user choice), classifiers, CHANGELOG,
   `python -m build` verification
3. **M7** — Security hardening: pip-audit + secret scanning + Dependabot
   (⚠ new dev deps)
4. **M8** — Onboarding: CONTRIBUTING.md, Makefile, examples/
5. **M10** — Extend `.ai/WORKFLOWS/` + `.ai/ROLES/` to full sets (audit §5)
6. **M11** — `.ai/PROMPTS/` (9 prompts; optional)
7. **M12** — Structure cleanup: artifact dirs (⚠ deletion approval),
   archive SESSION_BACKUP.md, GitHub templates
8. **M13** — Maintainability refactor: response helpers, data-driven MODEL_COSTS
9. **M14** — Architecture docs polish: Mermaid diagrams, normalization spec,
   extension guide
10. **M15** — Release v0.1.0: tag, release notes, optional PyPI (⚠ publish)

## Known follow-ups (need approval/decision)

- **RouterStage complexity fallback** — when custom routing rules exist but
  none match, the fallback rewrites the model to `gpt-*` (also affects
  LocalClient/Anthropic custom-rule paths). Fixing changes OpenAI routing
  behavior → needs a decision before M13/refactor work.

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
