# Workflow: Implement a Feature

_Owner: `.ai/ROLES/backend-engineer.md`, reviewed by `.ai/ROLES/reviewer.md`_
_Standards: coding, testing, documentation, git, ai-memory, checkpoint_
_Related: architecture-review, documentation-update; `.ai/DOD.md`_

## Purpose

Take a scoped, approved feature item from idea to shipped code with tests,
docs, and memory — the standard path for `feat:` commits.

## Prerequisites

- Feature item exists in `.ai/NEXT_STEPS.md` (or was requested by the user)
  with scope: what is in, what is out.
- No open approval blockers (architecture, dependencies, public API,
  package structure, deployment → approval required first).

## Steps

1. **Read state** — AGENTS.md startup procedure; read the milestone /
   NEXT_STEPS item and relevant `.ai/` docs.
2. **Check approvals** — gated areas (see Prerequisites) → stop and request
   approval before coding.
3. **Design (brief)** — note the approach in the session; architecture
   changes → DECISIONS.md entry via architecture-review (approval).
4. **Implement** — small, focused change per coding-standard; fail-open on
   every optimization path.
5. **Test** — add/adjust tests per testing-standard; cover the fail-open
   path and edge cases.
6. **Verify** — full gates (Verification).
7. **Document** — docstrings, README (user-facing), CHANGELOG
   (`[Unreleased]` → `Added`), and `.ai/` memory per documentation-update.
8. **Review** — self-review vs the code-review checklist; independent
   review when available.
9. **Commit** — small logical commit(s): `feat: <summary>` (git-standard).
10. **Push** — verify `git remote -v` (Decision 11); push.
11. **Checkpoint** — on milestone completion, write
    `.ai/CHECKPOINTS/CHECKPOINT_YYYYMMDD_HHMM.md` (checkpoint-standard).

## Verification

```bash
pytest tests/ -q
ruff check tokenopt tests
mypy tokenopt
```

## Expected outputs

- Feature code + tests + docs in the same commit(s)
- DoD-satisfied change (`.ai/DOD.md`)
- Memory updated; checkpoint on milestone completion

## Completion criteria

- [ ] Tests green (incl. new ones), lint + mypy clean
- [ ] Docs updated in the same commits
- [ ] Memory updated (CURRENT_STATE, SESSION_LOG, NEXT_STEPS)
- [ ] Committed + pushed
- [ ] Checkpoint created on milestone completion
