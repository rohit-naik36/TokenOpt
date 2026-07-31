# Workflow: Implement a Feature

_Owner: `.ai/ROLES/backend-engineer.md`, reviewed by `.ai/ROLES/reviewer.md`_
_Standards: coding, testing, documentation, git, ai-memory, checkpoint_

## Trigger

A feature item exists in `.ai/NEXT_STEPS.md` (or was requested by the user)
and has no open approval blockers.

## Steps

1. **Read state** — AGENTS.md startup procedure; read the milestone /
   NEXT_STEPS item and relevant `.ai/` docs. Confirm scope: what is in, what
   is out.
2. **Check approvals** — if the feature touches architecture, dependencies,
   public API, package structure, or deployment → stop and request approval
   before coding.
3. **Design (brief)** — note the approach in the session; if architecture
   changes, record a DECISIONS.md entry (approval required).
4. **Implement** — small, focused change; follow `.ai/STANDARDS/coding-standard.md`.
   Fail-open for any optimization path.
5. **Test** — add/adjust unit tests; cover the fail-open path; follow
   `.ai/STANDARDS/testing-standard.md`.
6. **Verify locally**
   ```bash
   pytest tests/ -q
   ruff check tokenopt tests
   ```
   (mypy after M1 fix.)
7. **Document** — update docstrings, README (if user-facing), and the
   appropriate `.ai/` files per `documentation-standard.md`.
8. **Commit** — small logical commit(s): `<type>: <summary>` (git-standard).
9. **Push** — verify `git remote -v` (Decision 11), push.
10. **Checkpoint** — on milestone completion, write
    `.ai/CHECKPOINTS/CHECKPOINT_YYYYMMDD_HHMM.md` (checkpoint-standard).

## Exit criteria

- [ ] Tests green (incl. new ones)
- [ ] Lint clean
- [ ] Docs updated (same commits)
- [ ] Memory updated (CURRENT_STATE, SESSION_LOG, NEXT_STEPS)
- [ ] Committed + pushed
- [ ] Checkpoint created on milestone completion
