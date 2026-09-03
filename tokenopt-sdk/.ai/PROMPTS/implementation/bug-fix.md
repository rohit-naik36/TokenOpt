# Prompt: Bug Fixing

_Group: implementation_
_Related: `.ai/WORKFLOWS/fix-bug.md`; owner: `.ai/ROLES/backend-engineer.md`_
_Standards: coding, testing, git, ai-memory; security defects: `.ai/WORKFLOWS/security-response.md`_

## Objective

Eliminate a defect at its root cause with a regression-proof failing test —
without changing the public contract.

## Required inputs

- Defect report: symptom, reproduction steps (or failing test),
  environment/version
- Affected area context: `.ai/ARCHITECTURE.md`, relevant module code,
  prior related decisions

## Instructions (deterministic)

1. Reproduce FIRST: write a test that demonstrates the bug (code defects)
   or capture the exact command/output (tooling defects).
2. Confirm the new test FAILS on the current code; record the failure
   output.
3. Diagnose the root cause by tracing the flow (`.ai/ARCHITECTURE.md`);
   do not patch the symptom.
4. Classify scope: if the fix changes public API or architecture → stop,
   request approval. Security-related defects → switch to
   `security-response` workflow; never log or print secrets.
5. Apply the smallest root-cause fix per coding-standard; fail-open
   preserved.
6. Verify:
   ```bash
   pytest tests/ -q
   ruff check tokenopt tests
   mypy tokenopt
   ```
7. Re-run the new test — must PASS post-fix (regression-proof).
8. Update docs (docstrings/comments explaining *why*; CHANGELOG
   `[Unreleased]` → `Fixed` when a release is near).
9. Commit `fix: <root cause summary>`; push after verifying
   `git remote -v` (Decision 11).
10. Record follow-up work in `.ai/NEXT_STEPS.md` if any remains.

## Expected outputs

- Failing test that passes post-fix
- Root-cause fix commit + push
- Docs/memory updated

## Verification criteria

- [ ] New test failed pre-fix, passes post-fix (proven, not assumed)
- [ ] Full suite green, lint + mypy clean
- [ ] No public API change without approval
- [ ] Commit message states the root cause, not the symptom

## Determinism rules

- The reproduction test is written before the fix — never after.
- If you cannot reproduce in 20 minutes of investigation, report back
  with evidence instead of guessing a fix.
