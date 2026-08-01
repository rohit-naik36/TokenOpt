# Next Steps

_Last updated: 2026-08-01 (M13 complete — structural refactoring under
behavioral freeze; M14 next)_

## M13 done — M14 next

M13 (Structural Refactoring & Architecture Stabilization) is complete and
verified: shared query/usage/shim helpers, typed stage configs, consolidated
pipeline composition (`_build_pipeline(routing_rule_filter)`), and the
few-shot module split — all behavior-preserving (167 tests, 94% coverage,
ruff/mypy/build/twine/examples green). Full report:
`.ai/M13_ARCHITECTURE_REVIEW.md` (hotspots H1–H11, assessment, debt report,
Immediate Recommendations, ADB-01..10).

1. **M14** — Architecture docs polish: Mermaid diagrams, normalization
   spec, extension guide
2. **M15** — Release v0.1.0: tag, release notes, optional PyPI (⚠ publish);
   run the M13 validation suite verbatim as the pre-release baseline; close
   audit P0.5 (pip-audit, Dependabot, secret scanning)
3. **Immediate Recs (from M13 §5.1)** — CI hardening (3.10–3.12 matrix,
   coverage gate, build+twine in CI), extension guide, keep metrics
   semantics frozen through v0.1.0

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
