# Next Steps

_Last updated: 2026-08-01 (M6 complete — release metadata ready)_

## M6 done — M7 is next (⚠ approval: new dev deps)

M6 (Release Metadata) is complete: MIT LICENSE (user decision), CHANGELOG.md
(Keep a Changelog, `[0.1.0] - 2026-08-01`), full `pyproject.toml` metadata
(author, keywords, 9 classifiers, project URLs, PEP 639 SPDX `license = "MIT"`
with `setuptools>=77` floor — Decision 17), README release-review updates
(providers table, extras, status, MIT license). Packaging verified end-to-end:
build ✅, `twine check` PASSED ✅, fresh-venv install + metadata ✅.
**M7 has an approval gate** (new dev deps: pip-audit, gitleaks, Dependabot).

1. **M7** — Security hardening: pip-audit + secret scanning + Dependabot
   (⚠ new dev deps)
2. **M8** — Onboarding: CONTRIBUTING.md (extend), Makefile, examples/
3. **M10** — Extend `.ai/WORKFLOWS/` + `.ai/ROLES/` to full sets (audit §5)
4. **M11** — `.ai/PROMPTS/` (9 prompts; optional)
5. **M12** — Structure cleanup: artifact dirs (⚠ deletion approval),
   archive SESSION_BACKUP.md, GitHub templates
6. **M13** — Maintainability refactor: response helpers, data-driven MODEL_COSTS
7. **M14** — Architecture docs polish: Mermaid diagrams, normalization spec,
   extension guide
8. **M15** — Release v0.1.0: tag, release notes, optional PyPI (⚠ publish)

## Notes

- Author name is currently the GitHub handle (`rohit-naik36`, Decision 17);
  personalize before publishing to PyPI.

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
