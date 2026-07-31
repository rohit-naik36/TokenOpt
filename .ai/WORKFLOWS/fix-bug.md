# Workflow: Fix a Bug

_Owner: `.ai/ROLES/backend-engineer.md`, reviewed by `.ai/ROLES/reviewer.md`_
_Standards: coding, testing, documentation, git, ai-memory_

## Trigger

A defect is reported (user, test failure, lint/type finding, audit finding).

## Steps

1. **Reproduce** — write the failing case first:
   - a test that demonstrates the bug (for code defects), or
   - the exact command/output (for tooling defects).
2. **Diagnose** — locate the root cause; trace through the pipeline
   (`ARCHITECTURE.md`) rather than patching the symptom.
3. **Confirm scope** — is it a defect or a missing feature? If the fix
   changes public API/architecture, stop and request approval.
4. **Fix** — smallest change that removes the root cause; follow
   coding-standard (fail-open preserved).
5. **Verify** — run the new test + full suite + lint:
   ```bash
   pytest tests/ -q
   ruff check tokenopt tests
   ```
6. **Regression-proof** — ensure the test fails on the pre-fix code (verify
   once, then keep the green result).
7. **Document** — update docstrings/comments (`why`), README if user-facing,
   and `CHANGELOG.md` (Fixes section) when a release is near.
8. **Commit** — `fix: <root cause summary>` (git-standard).
9. **Push** — verify remote (Decision 11); push.

## Exit criteria

- [ ] Failing test exists and passes post-fix
- [ ] Full suite green, lint clean
- [ ] Docs/memory updated
- [ ] Committed + pushed
- [ ] Note in SESSION_LOG + NEXT_STEPS if follow-up work remains
