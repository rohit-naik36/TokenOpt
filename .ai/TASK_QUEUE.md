# Task Queue

_Updated: 2026-08-01 (M3 DONE — Pipeline Stage Tests 2 complete)_

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

## IN PROGRESS

| Task | Notes |
|------|-------|
| (none — awaiting approval) | resume with M4 (⚠ approval: HTTP stub dev dep) |

## BLOCKED

| Task | Blocked by | Unblocked by |
|------|------------|--------------|
| (none) | — | — |

## READY

| # | Task | Depends on |
|---|------|------------|
| M4 | Integration tests + 80% coverage gate (⚠ new dev dep) | M2–M3 |
| M5 | CI pipeline (GitHub Actions, py 3.10–3.12) | M4 |
| M6 | Release metadata: license (⚠ user choice), CHANGELOG, build | M5 |
| M7 | Security: pip-audit + secret scan + Dependabot (⚠ dev deps) | M5 |
| M8 | Onboarding: CONTRIBUTING.md, Makefile, examples/ | — |
| M10 | Extend WORKFLOWS/ + ROLES/ to full sets | — |
| M11 | `.ai/PROMPTS/` (optional) | M10 |
| M12 | Cleanup: artifact dirs (⚠ deletion), archive SESSION_BACKUP.md, templates | — |
| M13 | Refactor: response helpers, data-driven MODEL_COSTS | M4 |
| M14 | Arch docs: Mermaid, normalization spec, extension guide | M13 |
| M15 | Release v0.1.0: tag, notes, optional PyPI (⚠ publish) | M6–M14 |

## Blocked-by-approval backlog

- M4 (HTTP stub dev dep) — future approval
- M6 (license choice) — user decides MIT or other
- M12 (deleting 7 artifact dirs + archiving SESSION_BACKUP.md)
- M15 (PyPI publish — optional)
