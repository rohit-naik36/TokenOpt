# Next Steps

_Last updated: 2026-08-02 (M15 complete — v0.1.0 released to PyPI; ADB
backlog next)_

## M15 done — v0.1.0 live on PyPI

M15 released v0.1.0: Trusted Publisher (OIDC, Decision 26) configured on
PyPI for `tokenopt` / `rohit-naik36` / `publish.yml`, tag `v0.1.0` pushed,
workflow built sdist+wheel, `twine check` passed, uploaded via
`pypa/gh-action-pypi-publish` — verified live at
`https://pypi.org/pypi/tokenopt/json`. No API tokens stored. Dependabot
action PRs merged. README already documents `pip install tokenopt`.

1. **ADB backlog (post-v0.1.0)** — consume ADB items: High — ADB-03 plugin
   architecture, ADB-11 internal architecture contracts; Medium — ADB-01,
   ADB-02, ADB-05, ADB-12, ADB-13.
2. Post-v0.1.0 roadmap items per ROADMAP Phase 2 (router cost/latency
   tracking, cache file persistence, pluggable summarizer, real LLMLingua,
   local streaming, Prometheus exporter).

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

- None blocking — v0.1.0 released to PyPI (Decision 26, user-approved).

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
