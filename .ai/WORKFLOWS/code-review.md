# Workflow: Code Review

_Owner: `.ai/ROLES/reviewer.md`_
_Standards: coding, testing, documentation, git, security_
_Related: architecture-review (design-level), uat-execution (acceptance); `.ai/DOD.md`_

## Purpose

Independently validate that a change is correct, complete, and compliant
before it is considered done — the gate between "implemented" and "done".

## Prerequisites

- A feature/fix/refactor commit or milestone is complete and awaiting
  review.
- Reviewer is not the author (self-review is a minimum bar; independent
  review is the norm).

## Steps

1. **Scope** — the diff is one logical change; no unrelated edits; no giant
   commits.
2. **Correctness** — behavior matches the requirement; edge cases (empty
   input, fail-open paths) handled.
3. **Quality** — coding-standard: hints, naming, module size, no *what*
   comments; no duplicated logic where a helper exists.
4. **Tests** — change is covered; the test fails without the change; error
   paths tested; no timing assertions.
5. **Docs** — docstrings/README/`.ai/` updated in the same commit; memory
   current.
6. **Security** — no secrets, no logging of keys/prompts, no unbounded
   dependencies, remote policy respected (Decision 11); scanner findings
   escalate to security-reviewer.
7. **API stability** — drop-in contract untouched without approval.
8. **Verify** — run (or confirm) the full gates:
   ```bash
   pytest tests/ -q
   ruff check tokenopt tests
   mypy tokenopt
   ```

## Verification

Gates above; verdict recorded in SESSION_LOG with finding list.

## Expected outputs

- Verdict: **Approve** / **Request changes** (Blocking vs Non-blocking) /
  **Escalate** (Approval Gate topics → user)
- Finding list routed to the author or NEXT_STEPS

## Completion criteria

- [ ] Every checklist item applied
- [ ] Verdict recorded
- [ ] Blocking findings block commit until resolved
- [ ] Non-blocking findings recorded in NEXT_STEPS

## Rules

- Review the code, not the author.
- A reviewer must not have authored the change being reviewed.
- Findings are documented in the session log; blocking findings block commit.
