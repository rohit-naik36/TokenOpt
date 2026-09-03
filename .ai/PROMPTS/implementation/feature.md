# Prompt: Feature Implementation

_Group: implementation_
_Related: `.ai/WORKFLOWS/implement-feature.md`; owner: `.ai/ROLES/backend-engineer.md`_
_Standards: coding, testing, documentation, git, ai-memory, checkpoint_

## Objective

Ship a scoped feature item as small logical commits with tests, docs, and
memory updated in the same commits — meeting every Definition of Done item
(`.ai/DOD.md`).

## Required inputs

- The feature item from `.ai/NEXT_STEPS.md` (or user request) with scope:
  in / out, acceptance criteria
- Project state: `.ai/CURRENT_STATE.md`, `.ai/DECISIONS.md`,
  `.ai/ARCHITECTURE.md`
- Green baseline suite

## Instructions (deterministic)

1. Read the AGENTS.md startup procedure files (in order) before coding.
2. Check Approval Gates: architecture / dependencies / public API /
   package structure / deployment → stop and request approval FIRST.
3. State the design in ≤ 10 lines in the session; architecture changes get
   a DECISIONS.md entry via `design/architecture-review.md`.
4. Implement the change in small focused increments per
   `.ai/STANDARDS/coding-standard.md`; fail-open preserved on every
   optimization path.
5. Add tests per `.ai/STANDARDS/testing-standard.md` (unit + integration
   as applicable); cover edge cases and the fail-open path.
6. Verify before ANY commit:
   ```bash
   pytest tests/ -q
   ruff check tokenopt tests
   mypy tokenopt
   ```
7. Update docs (docstrings, README if user-facing, CHANGELOG `[Unreleased]`
   → `Added`) in the same commit.
8. Commit `feat: <summary>` (imperative, ≤ 72 chars); push after
   verifying `git remote -v` (Decision 11).
9. Update `.ai/` memory (CURRENT_STATE, SESSION_LOG, NEXT_STEPS); on
   milestone completion create a checkpoint
   `.ai/CHECKPOINTS/CHECKPOINT_YYYYMMDD_HHMM.md`.

## Expected outputs

- Code + tests + docs in the same logical commits
- `feat:` commit(s) pushed to origin/main
- Memory updated; checkpoint on milestone completion

## Verification criteria

- [ ] `pytest tests/ -q` green (new tests included)
- [ ] `ruff check tokenopt tests` clean
- [ ] `mypy tokenopt` exit 0
- [ ] Coverage gate ≥ 80% met
- [ ] DoD checklist complete (`.ai/DOD.md`)

## Determinism rules

- One logical change per commit; never one giant commit.
- Do not commit until all three gates pass.
