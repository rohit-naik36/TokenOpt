# Next Steps

_Last updated: 2026-08-01 (M5 complete — CI pipeline green on GitHub)_

## M5 done — M6 is next (⚠ approval: license choice)

M5 (Continuous Integration) is complete: `.github/workflows/ci.yml` with
lint / test (matrix 3.10–3.12) / package jobs running the full DoD gate
pipeline; CI verified green via GitHub API (run 30664914071); two CI-found
defects fixed (ollama mypy override, clear error for missing ollama package —
Decision 16); CONTRIBUTING.md documents the pipeline, assumptions, and branch
protection recommendations. **M6 has an approval gate** (license choice).

1. **M6** — Release metadata: license (⚠ user choice), classifiers, CHANGELOG,
   `python -m build` verification
2. **M7** — Security hardening: pip-audit + secret scanning + Dependabot
   (⚠ new dev deps)
3. **M8** — Onboarding: CONTRIBUTING.md (extend), Makefile, examples/
4. **M10** — Extend `.ai/WORKFLOWS/` + `.ai/ROLES/` to full sets (audit §5)
5. **M11** — `.ai/PROMPTS/` (9 prompts; optional)
6. **M12** — Structure cleanup: artifact dirs (⚠ deletion approval),
   archive SESSION_BACKUP.md, GitHub templates
7. **M13** — Maintainability refactor: response helpers, data-driven MODEL_COSTS
8. **M14** — Architecture docs polish: Mermaid diagrams, normalization spec,
   extension guide
9. **M15** — Release v0.1.0: tag, release notes, optional PyPI (⚠ publish)

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
