# Task Queue

_Updated: 2026-08-01 01:40 (M1 DONE — Verification Gates complete)_

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

## IN PROGRESS

| Task | Notes |
|------|-------|
| (none — awaiting approval) | resume with M2 |

## BLOCKED

| Task | Blocked by | Unblocked by |
|------|------------|--------------|
| (none) | — | — |

## READY

| # | Task | Depends on |
|---|------|------------|
| M2 | Pipeline stage tests 1: router, compressor, summarizer | — |
| M3 | Pipeline stage tests 2: cache, RAG, few-shot | M2 |
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
