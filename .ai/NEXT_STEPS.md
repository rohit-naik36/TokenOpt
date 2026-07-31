# Next Steps

_Last updated: 2026-08-01 (M7 complete — security baseline in place)_

## M7 done — M8 is next (no approval gate)

M7 (Security Baseline) is complete: author metadata personalized to
**Rohit Naik** (pyproject + LICENSE), `pip-audit` in the `dev` extra +
security CI job, `gitleaks` pinned 8.30.1 full-history scan in CI,
`.github/dependabot.yml` (pip + github-actions, weekly), and `SECURITY.md`
(supported versions, private reporting, scope, coordinated disclosure,
release-blocker vs advisory policy). Local scans clean: pip-audit zero
findings, gitleaks 58 commits / no leaks. CI security job green (Decision 18).

1. **M8** — Onboarding: CONTRIBUTING.md (extend), Makefile, examples/
2. **M10** — Extend `.ai/WORKFLOWS/` + `.ai/ROLES/` to full sets (audit §5)
3. **M11** — `.ai/PROMPTS/` (9 prompts; optional)
4. **M12** — Structure cleanup: artifact dirs (⚠ deletion approval),
   archive SESSION_BACKUP.md, GitHub templates
5. **M13** — Maintainability refactor: response helpers, data-driven MODEL_COSTS
6. **M14** — Architecture docs polish: Mermaid diagrams, normalization spec,
   extension guide
7. **M15** — Release v0.1.0: tag, release notes, optional PyPI (⚠ publish)

## Notes

- Author metadata now uses the publisher name **Rohit Naik** (pyproject
  `authors`, LICENSE copyright) — prerequisite applied at M7 start.
- **Dependabot is active**: it opened initial update PRs for
  `actions/checkout`, `actions/setup-python`, and `actions/upload-artifact`
  (v4/v5 → v7). Merge after review when convenient; they are not blockers.

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
