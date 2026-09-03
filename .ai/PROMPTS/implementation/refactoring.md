# Prompt: Refactoring

_Group: implementation_
_Related: `.ai/WORKFLOWS/refactoring.md`; owner: `.ai/ROLES/backend-engineer.md`_
_Standards: coding, testing, git, documentation_

## Objective

Improve internal structure, readability, or maintainability with ZERO
behavior change and ZERO public API change — a refactor that changes
behavior is a feature or a fix, not a refactor.

## Required inputs

- The refactor target (module/function list, or the audit finding driving it)
- Green pre-change baseline (suite + lint + types)
- `.ai/DOD.md` (completion authority)

## Instructions (deterministic)

1. Record the baseline gate result BEFORE touching code:
   ```bash
   pytest tests/ -q
   ruff check tokenopt tests
   mypy tokenopt
   ```
2. Confirm scope is behavior-preserving; public API / architecture /
   package structure changes → stop, request approval.
3. Refactor in small increments: extract helpers instead of duplicating
   logic; remove *what* comments; keep fail-open on every optimization
   path; do not "improve" naming in unrelated code.
4. After EACH increment, run the affected tests; after all increments, run
   the full gates (step 1 commands).
5. Add tests ONLY if the refactor exposes uncovered paths — do not inflate
   the diff with test rewrites that change assertions.
6. Update docstrings/comments; `CHANGELOG.md` `[Unreleased]` → `Changed`
   only if user-visible (rare for a refactor).
7. Commit `refactor: <what changed and why>`; push after verifying
   `git remote -v` (Decision 11).
8. Record in `.ai/SESSION_LOG.md` and update `.ai/CURRENT_STATE.md`.

## Expected outputs

- Behavior-identical code, cleaner structure
- Green suite at ≥ baseline coverage (≥ 80% gate)
- `refactor:` commit + push + memory entry

## Verification criteria

- [ ] Suite green before and after (identical behavior)
- [ ] `ruff` + `mypy` clean
- [ ] Coverage ≥ baseline
- [ ] Diff touches only the refactor scope
- [ ] No public API change without approval

## Determinism rules

- If any gate was red before you started, STOP and report — never refactor
  on a red baseline.
- Run gates after each increment, not once at the end.
