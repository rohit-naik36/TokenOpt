# Next Steps

_Last updated: 2026-08-01 (M12 repository curation complete; M13 next)_

## M12 done — M13 next

M12 complete: 7 empty artifact dirs + all generated artifacts (`dist/`,
`tokenopt.egg-info/`, `.coverage`, caches, `__pycache__/`) deleted;
`SESSION_BACKUP.md` archived to `.ai/ARCHIVE/` (git mv, history intact);
`.ai/REPOSITORY_RETENTION_POLICY.md` (permanent / archived / regenerated /
disposable / user-owned) + `.ai/REPOSITORY_INVENTORY.md` (classification
+ deletion ledger) created; GitHub PR/issue templates + CODEOWNERS added;
audit findings 6 + 9 and plan item 8 closed (dated §7); GOVERNANCE_INDEX
Policies section; repository-audit workflow gains curation step. Root tree
contains only intentional entries; suite 158 green; SDK untouched.
Retention policy Decision → see DECISIONS.md (Decision 23).

1. **M13** — Maintainability refactor (behavior-preserving): response
   helpers, data-driven MODEL_COSTS (⚠ confirm RouterStage fallback
   decision first — known follow-up below)
2. **M14** — Architecture docs polish: Mermaid diagrams, normalization
   spec, extension guide
3. **M15** — Release v0.1.0: tag, release notes, optional PyPI (⚠ publish)

## Notes

- Prompt library "live" status: prompts are validated by construction
  (instantiate the workflows they reference); record real-task usage in
  SESSION_LOG per `.ai/PROMPTS/README.md` maintenance rule.
- Curation passes are periodic (repository-audit workflow); deletions
  always follow `.ai/REPOSITORY_RETENTION_POLICY.md`.

## Notes

- Author metadata now uses the publisher name **Rohit Naik** (pyproject
  `authors`, LICENSE copyright) — applied at M7 start.
- **Dependabot is active**: it opened initial update PRs for
  `actions/checkout`, `actions/setup-python`, and `actions/upload-artifact`
  (v4/v5 → v7). Merge after review when convenient; they are not blockers.
- README documents install-from-git until PyPI publish (M15).

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
