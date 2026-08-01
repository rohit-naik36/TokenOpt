# Next Steps

_Last updated: 2026-08-01 (M10 governance expansion complete; M11 optional, M12 next)_

## M10 done — M11 (optional) or M12 (⚠) next

M10 complete: WORKFLOWS 5 → 14 (9 new runbooks on a unified template with
standardized gates), ROLES 4 → 11 (7 new roles with authority/inputs/
success criteria), `.ai/GOVERNANCE_INDEX.md` (machine-consumable registry
+ ownership matrix + handoff map) and `.ai/GOVERNANCE_REVIEW.md` (findings
I1–I8 + multi-agent validation). All links verified, all workflow owners
resolve to real roles, SDK untouched, suite 158 green. Decision 21.

1. **M11** — `.ai/PROMPTS/` (9 reusable prompts; optional)
2. **M12** — Structure cleanup: artifact dirs (⚠ deletion approval),
   archive SESSION_BACKUP.md, GitHub templates
3. **M13** — Maintainability refactor: response helpers, data-driven MODEL_COSTS
4. **M14** — Architecture docs polish: Mermaid diagrams, normalization spec,
   extension guide
5. **M15** — Release v0.1.0: tag, release notes, optional PyPI (⚠ publish)

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
