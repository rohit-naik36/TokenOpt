# Task Queue

_Updated: 2026-08-01 (M6 DONE — Release Metadata complete)_

Statuses: `READY` · `IN PROGRESS` · `BLOCKED` · `DONE`
Tasks map to milestones in `.ai/IMPLEMENTATION_ROADMAP.md`.

## DONE

| Task | Notes |
|------|-------|
| Baseline v0.1.0 (Phase 1) | 23 tests, lint clean, build OK |
| Git repo + 17→24 commits + push | `rohit-naik36/TokenOpt` |
| `.ai/` memory foundation (7 docs + manifest + AGENTS.md) | — |
| Repository audit | `REPOSITORY_AUDIT.md`, overall 6.4/10 |
| Implementation roadmap | approved with Phase 0 modification |
| **M0.1** — `.ai/STANDARDS/` (8 files) | — |
| **M0.2** — `.ai/WORKFLOWS/` (5 files) | — |
| **M0.3** — `.ai/ROLES/` (4 files) | — |
| Manifest + AGENTS.md references | §4/§8/§9 + startup procedure |
| Session management policy adopted | Decision 12, this queue + SESSION_STATE.md |
| **M1** — Verification Gates | `mypy tokenopt` exit 0; numpy pin `>=1.24,<2.5`; 37 typing fixes + latent summarizer bug; `.ai/DOD.md` ratified; docs gates updated |
| **M2** — Pipeline Stage Tests 1 | 54 new behavioral-contract tests (router 18, compressor 16, summarizer 13, gating 5); router/compressor coverage 27%/… → **100%**; **defect fixed**: summarizer kept oldest messages as recent (now keeps last 3); suite 77 passed |
| **M3** — Pipeline Stage Tests 2 | 53 new tests (cache 18, RAG 15, few-shot 13, gating+7); cache 68%→**96%**, rag_optimizer 24%→**98%**, suite **89%**; **4 defects fixed**: cache key collision (non-string content), RAG dedup embedding misalignment, few-shot injection w/o system message, pipeline fail-open; suite 130 passed |
| **M4** — Integration Tests + Coverage Gate | `INTEGRATION_TEST_STRATEGY.md`; `tests/integration/` 19 tests via `httpx.MockTransport` (**zero new deps** — `http_client=` kwarg); **2 defects fixed**: `chat.completions.create` drop-in surface (Decision 14), Anthropic router scoped to claude models (Decision 13); `[tool.coverage] fail_under=80` + `--cov` addopts; suite **149 passed, coverage 94%** |
| **M5** — CI Pipeline | `.github/workflows/ci.yml` — lint / test matrix (3.10–3.12) / package+build+smoke; `CONTRIBUTING.md` (CI docs + branch protection notes); README badge; **verified green on GitHub** (run 30664914071); **2 CI-found defects fixed** (ollama mypy override; clear error for missing ollama — Decision 16); suite **150 passed, coverage 94%** |
| **M6** — Release Metadata | MIT LICENSE (user decision); CHANGELOG.md (Keep a Changelog, `[0.1.0]`); pyproject metadata complete (author, keywords, 9 classifiers, URLs, PEP 639 `license = "MIT"`, `setuptools>=77` — Decision 17); README release review (providers/extras/status/license); **build ✅ + `twine check` PASSED + fresh-venv metadata ✅**; suite **150 passed, coverage 94%** |

## IN PROGRESS

| Task | Notes |
|------|-------|
| (none — awaiting approval) | resume with M7 (⚠ approval: pip-audit/gitleaks/Dependabot dev deps) |

## BLOCKED

| Task | Blocked by | Unblocked by |
|------|------------|--------------|
| (none) | — | — |

## READY

| # | Task | Depends on |
|---|------|------------|
| M10 | Extend WORKFLOWS/ + ROLES/ to full sets | — |
| M11 | `.ai/PROMPTS/` (optional) | M10 |
| M12 | Cleanup: artifact dirs (⚠ deletion), archive SESSION_BACKUP.md, templates | — |
| M13 | Refactor: response helpers, data-driven MODEL_COSTS | M4 |
| M14 | Arch docs: Mermaid, normalization spec, extension guide | M13 |
| M15 | Release v0.1.0: tag, notes, optional PyPI (⚠ publish) | M6–M14 |

## Blocked-by-approval backlog

- M12 (deleting 7 artifact dirs + archiving SESSION_BACKUP.md)
- M15 (PyPI publish — optional)
- Merge Dependabot action-upgrade PRs (checkout/setup-python/upload-artifact
  → v7) — opened 2026-08-01, not blockers
- RouterStage complexity-fallback hole (custom rules + no match → gpt-*
  rewrite; shared with LocalClient/Anthropic custom-rule paths) — needs a
  routing-behavior decision before refactor work
