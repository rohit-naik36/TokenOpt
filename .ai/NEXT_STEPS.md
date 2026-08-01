# Next Steps

_Last updated: 2026-08-01 (Post-M8 UAT refinements complete; M10 next)_

## UAT refinements done — M10 is next (governance docs; no gate)

Post-M8 UAT refinements complete: per-request metrics now separate
compression attempted/effective + tokens saved + reduction % + model
latency split (additive fields, no API break); all examples print concise
readable output (JSON preserved for production); `local_basic.py`
demonstrates cache miss→hit; README has a 5-Minute Quick Start;
**docs/UAT.md** is the permanent release acceptance checklist; 5 regression
tests added (155 total). All gates green.

1. **M10** — Extend `.ai/WORKFLOWS/` + `.ai/ROLES/` to full sets (audit §5)
2. **M11** — `.ai/PROMPTS/` (9 prompts; optional)
3. **M12** — Structure cleanup: artifact dirs (⚠ deletion approval),
   archive SESSION_BACKUP.md, GitHub templates
4. **M13** — Maintainability refactor: response helpers, data-driven MODEL_COSTS
5. **M14** — Architecture docs polish: Mermaid diagrams, normalization spec,
   extension guide
6. **M15** — Release v0.1.0: tag, release notes, optional PyPI (⚠ publish)

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
