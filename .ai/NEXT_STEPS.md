# Next Steps

_Last updated: 2026-08-01 (routing precedence decision done — Decision 24; M13 next)_

## Pre-M13 decision done — M13 next

The RouterStage precedence contract is decided (Decision 24, principle of
least surprise): explicit caller model wins; matching rule wins by
priority; custom rules with no match preserve the caller's model (never
rewritten — no more `gpt-*` rewrites on Anthropic/local); no custom rules
→ built-in complexity routing; provider default last. Implemented,
tested (167 green), examples validated against the stub server, review in
`.ai/ROUTING_PRECEDENCE_REVIEW.md`.

1. **M13** — Maintainability refactor (behavior-preserving): response
   helpers, data-driven MODEL_COSTS — the routing block is now cleared
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

- **M15 (PyPI) publish gate** — whether v0.1.0 ships to PyPI or stays
  install-from-git. Decide at M15 start.

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
