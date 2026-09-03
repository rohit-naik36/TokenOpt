# Next Steps

_Last updated: 2026-08-01 (M14 complete — Architecture Knowledge Base;
M15 next)_

## M14 done — M15 next

M14 built the permanent Architecture Knowledge Base at
`.ai/KNOWLEDGE_BASE/` (10 files: system overview, request lifecycle with
Mermaid, pipeline, provider layer + normalization spec, configuration,
metrics, normative architectural contracts C1–C8, extension guide, internal
assessment + ADB-11..13). Docs-only — no runtime code changed; Decision 24
paths, metrics vocabulary, and config cross-checked against code.

1. **M15** — Release v0.1.0: tag, release notes, optional PyPI (⚠ publish
   gate at start). Run the M13 validation suite verbatim as the
   pre-release regression baseline; close audit P0.5 (pip-audit, Dependabot
   merges, secret scanning); CI hardening per M13 Immediate Recs
   (3.10–3.12 matrix, hard coverage gate, build+twine in CI).
2. **ADB backlog (post-v0.1.0)** — consume ADB items: High — ADB-03 plugin
   architecture, ADB-11 internal architecture contracts; Medium — ADB-01,
   ADB-02, ADB-05, ADB-12, ADB-13.

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
