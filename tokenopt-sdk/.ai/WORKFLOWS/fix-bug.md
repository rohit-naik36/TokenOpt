# Workflow: Fix a Bug

_Owner: `.ai/ROLES/backend-engineer.md`, reviewed by `.ai/ROLES/reviewer.md`_
_Standards: coding, testing, documentation, git, ai-memory, checkpoint_
_Related: regression-verification, security-response (security defects); `.ai/DOD.md`_

## Purpose

Eliminate a defect at the root cause with a failing-test proof, without
changing the public contract.

## Prerequisites

- A defect report exists (user, test failure, lint/type finding, audit
  finding, scanner alert).
- Reproduction known or discoverable.

## Steps

1. **Reproduce** — write the failing case first:
   - a test that demonstrates the bug (code defects), or
   - the exact command/output (tooling defects).
2. **Diagnose** — locate the root cause; trace through the pipeline
   (`ARCHITECTURE.md`) rather than patching the symptom.
3. **Confirm scope** — defect or missing feature? Public API / architecture
   changes → stop and request approval.
4. **Fix** — smallest change that removes the root cause per
   coding-standard; fail-open preserved.
5. **Verify** — full gates (Verification); the new test must fail on the
   pre-fix code (prove once, keep the green result).
6. **Document** — docstrings/comments (`why`), README if user-facing,
   CHANGELOG `[Unreleased]` → `Fixed` when a release is near.
7. **Commit** — `fix: <root cause summary>` (git-standard).
8. **Push** — verify remote (Decision 11); push.
9. **Hand off** — note in SESSION_LOG + NEXT_STEPS if follow-up work
   remains; security-related fixes follow security-response.

## Verification

```bash
pytest tests/ -q
ruff check tokenopt tests
mypy tokenopt
```

## Expected outputs

- Failing test that passes post-fix (regression-proof)
- Root-cause fix, docs, and memory updated
- Fix commit + push

## Completion criteria

- [ ] Failing test exists and passes post-fix
- [ ] Full suite green, lint + mypy clean
- [ ] Docs/memory updated
- [ ] Committed + pushed
- [ ] Follow-up work recorded if any
