# Workflow: Code Review

_Owner: `.ai/ROLES/reviewer.md`_
_Standards: coding, testing, documentation, git, security_

## Trigger

A feature/fix commit or milestone is complete and awaiting review
(self-review for single-agent work; independent reviewer when available).

## Review checklist

1. **Scope** — the diff is one logical change; no unrelated edits; no giant
   commits.
2. **Correctness** — behavior matches the requirement; edge cases (empty
   input, fail-open paths) handled.
3. **Quality** — follows coding-standard: hints, naming, module size,
   no *what* comments; no duplicated logic where a helper exists.
4. **Tests** — the change is covered; the test fails without the change;
   error paths tested; no timing assertions.
5. **Docs** — docstrings/README/`.ai/` updated in the same commit; memory is
   current.
6. **Security** — no secrets, no logging of keys/prompts, no unbounded
   dependencies added, remote policy respected (Decision 11).
7. **API stability** — drop-in contract untouched without approval.
8. **Verification** — run (or confirm) locally:
   ```bash
   pytest tests/ -q
   ruff check tokenopt tests
   ```

## Outcomes

- **Approve** — record in SESSION_LOG; milestone can proceed.
- **Request changes** — list findings as: Blocking (must fix before merge) /
  Non-blocking (follow-up item to NEXT_STEPS).
- **Escalate** — anything touching an Approval Gate goes back to the user.

## Rules

- Review the code, not the author.
- A reviewer must not have authored the change being reviewed
  (self-review is a minimum bar; independent review is the norm).
- Findings are documented in the session log; blocking findings block commit.
