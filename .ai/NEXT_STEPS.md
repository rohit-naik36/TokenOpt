# Next Steps

_Last updated: 2026-08-01 (M11 prompt library complete; M12 next, ⚠ deletion approval)_

## M11 done — M12 (⚠) next

M11 complete: `.ai/PROMPTS/` holds 10 prompts grouped by purpose
(design / implementation / verification / operations), each with
objective, required inputs, deterministic instructions (exact commands +
paths), expected outputs, verification criteria, and determinism rules;
`.ai/PROMPTS/README.md` codifies the design guidelines (template, layer
model, add/maintain rules); GOVERNANCE_INDEX gains the Prompts table;
all cross-references resolve; SDK untouched; suite 158 green.
Decision 22.

1. **M12** — Structure cleanup: artifact dirs (⚠ deletion approval),
   archive SESSION_BACKUP.md, GitHub templates
2. **M13** — Maintainability refactor: response helpers, data-driven MODEL_COSTS
3. **M14** — Architecture docs polish: Mermaid diagrams, normalization spec,
   extension guide
4. **M15** — Release v0.1.0: tag, release notes, optional PyPI (⚠ publish)

## Notes

- Prompt library "live" status: prompts are validated by construction
  (instantiate the workflows they reference); record real-task usage in
  SESSION_LOG per `.ai/PROMPTS/README.md` maintenance rule.

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
