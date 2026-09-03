# Definition of Done (DoD) — TokenOpt SDK

_Last updated: 2026-08-01_
_Status: Ratified with Milestone M1 (Verification Gates)_
_Scope: every milestone, feature, and fix committed to this repository_

This document is the permanent, binding completion checklist for all future
work. It operationalizes `.ai/PROJECT_MANIFEST.md` §7 (Definition of Done) and
is enforced by the commit and push rules in `AGENTS.md`, `.ai/STANDARDS/`.

---

## 1. The verification gate

A change is committed **only** when every check below is demonstrably green.
Run them in this order; a failure stops the commit.

| # | Gate | Command | Pass condition |
|---|------|---------|----------------|
| 1 | Unit/integration tests | `pytest tests/` | All tests pass, 0 failures |
| 2 | Lint | `ruff check tokenopt tests` | Zero findings |
| 3 | Type check | `mypy tokenopt` | Exit code 0 |
| 4 | Package build | `python -m build` | sdist + wheel produced |
| 5 | Install + smoke | install the built wheel in a **fresh venv**, then `import tokenopt` | Import succeeds, version reported |

Gate 5 is required before any release (M15) and on every milestone that
touches packaging or `pyproject.toml`; on other milestones it is recommended
but may be deferred with a recorded reason.

## 2. Definition of Done checklist

Every milestone or feature is **done** only when **all** of the following are
true:

- [ ] Implementation completed and self-reviewed (coding standard)
- [ ] `pytest tests/` green (gate 1)
- [ ] `ruff check tokenopt tests` clean (gate 2)
- [ ] `mypy tokenopt` exit 0 (gate 3)
- [ ] `python -m build` succeeds when packaging changed (gate 4)
- [ ] Fresh-venv install + import smoke test passed (gate 5)
- [ ] Docstrings/README updated as applicable
- [ ] Project memory updated (`.ai/CURRENT_STATE.md`, `.ai/NEXT_STEPS.md`,
      `.ai/SESSION_LOG.md`, `.ai/SESSION_STATE.md`, `.ai/TASK_QUEUE.md`)
- [ ] Architecture/decisions updated if the change affects them
- [ ] Checkpoint created for the milestone (`.ai/CHECKPOINTS/`)
- [ ] Committed in small logical commits with conventional messages
- [ ] Pushed to GitHub (remote verified per Decision 11)

## 3. Non-negotiables

- **A red suite is a blocked merge.** Never commit with failing tests, lint
  findings, or a non-zero mypy exit.
- **No silent waivers.** A gate can be skipped only with explicit user
  approval, and the waiver must be recorded in the commit message and the
  session log.
- **The numpy pin (`numpy>=1.24,<2.5`) and the optional-extras mypy
  overrides in `pyproject.toml` are intentional** (see
  `.ai/DECISIONS.md`-style note in the M1 checkpoint); do not remove them
  without a decision.
- **No new features or refactors beyond milestone scope.** M1 and its
  successors fix gates; product behavior changes ship via the roadmap only.

## 4. M1 provenance (why this document exists)

M1 (Verification Gates) established the reproducible local pipeline: the mypy
gate was broken (numpy 2.5 stubs vs the declared Python 3.10 target), and 37
real typing findings plus one latent runtime bug (ContextSummarizerStage
receiving a config where a callable was expected) were fixed. This document
locks the resulting gates in place so M2–M15 each start from a verifiable
baseline.

## 5. Related documents

- `.ai/IMPLEMENTATION_ROADMAP.md` — milestone ceremony references this DoD
- `.ai/STANDARDS/testing-standard.md`, `git-standard.md`, `coding-standard.md`
- `AGENTS.md` — Git Rules (commit gate), Session Close Procedure
