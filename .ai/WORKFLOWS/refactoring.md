# Workflow: Refactoring

_Owner: `.ai/ROLES/backend-engineer.md`, reviewed by `.ai/ROLES/reviewer.md`_
_Standards: coding, testing, git, documentation, ai-memory, checkpoint_
_Related: implement-feature, fix-bug, code-review; `.ai/DOD.md`_

## Purpose

Improve internal structure, readability, or maintainability WITHOUT changing
behavior or the public API. A refactor that changes behavior is a feature or
a fix, not a refactor.

## Prerequisites

- Refactor item exists in `.ai/NEXT_STEPS.md` (or audit finding), or the
  change rides along a related feature/fix commit.
- The pre-refactor suite is green (behavior baseline).

## Steps

1. **Scope** — confirm the refactor is behavior-preserving; if it touches
   public API, architecture, or package structure → stop and request
   approval (Approval Gates).
2. **Baseline** — record the pre-change test result:
   ```bash
   pytest tests/ -q
   ```
3. **Refactor** — small, focused change per coding-standard; extract
   helpers instead of duplicating logic; no *what* comments; fail-open
   preserved on every optimization path.
4. **Verify** — full gates (see Verification). Coverage must not drop below
   the gate; add tests only if the refactor reveals uncovered paths.
5. **Review** — self-review against the code-review checklist; record a
   blocking/non-blocking verdict for larger refactors.
6. **Document** — docstrings/comments updated; `CHANGELOG.md` under
   `[Unreleased]` → `Changed` when user-visible; `.ai/` memory updated.
7. **Commit** — `refactor: <what changed and why>` (git-standard).
8. **Push** — verify `git remote -v` (Decision 11); push.

## Verification

```bash
pytest tests/ -q
ruff check tokenopt tests
mypy tokenopt
```

## Expected outputs

- Refactored code with identical behavior
- Green suite + clean lint/types at the same coverage level or higher
- Commit + memory entry

## Completion criteria

- [ ] Behavior preserved (suite green before and after)
- [ ] Lint + mypy clean
- [ ] No public API / architecture change without approval
- [ ] Coverage gate ≥ 80% still met
- [ ] Committed + pushed
