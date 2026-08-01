# Task Queue

_Updated: 2026-08-01 (M8.2 DONE — Value Demonstration & Showcase complete)_

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
| **M7** — Security Baseline | author → "Rohit Naik"; pip-audit 0 vulns + CI security job; gitleaks 8.30.1 full-history (58 commits, no leaks); dependabot.yml weekly; SECURITY.md; CONTRIBUTING security section; CI run 30666354747 all green; suite **150 passed, coverage 94%** |
| **M8** — Onboarding | examples/ (6 scripts); README rewrite (Quick Start, extras, FAQ); Makefile; CONTRIBUTING; clean-env validation vs stub server (6/6 exit 0); defect fixed (F821 in metrics_observability.py); suite **150 passed, coverage 94%** |
| Post-M8 UAT refinements | metrics clarity (attempted/effective/tokens_saved/reduction_pct/model_latency_ms — additive); _format.py readable blocks; 5-Minute Quick Start; docs/UAT.md; +5 regression tests (155 total); suite **155 passed, coverage 94%** |
| **M8.2** — Value Demonstration & Showcase | `RequestMetrics.routing_reason` (additive, from ctx.metrics — rule name or `complexity-based (low|medium|high)`); `_format.py` `explain()` + `print_comparison()`; 6 examples rewritten as value demos (header docstrings, long prompts, OFF vs ON + miss→hit, truthful explanations); README/CHANGELOG; +3 regression tests (158 total); clean-env validation 6/6 exit 0, cross-checked truthful; commits `203b3d4`/`ec4f638`/`2a6093f`; suite **158 passed, coverage 94%**, CI green |

## IN PROGRESS

| Task | Notes |
|------|-------|
| (none) | M10 is next (no approval gate) |

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
