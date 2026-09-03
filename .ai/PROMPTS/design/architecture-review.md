# Prompt: Architecture Review

_Group: design_
_Related: `.ai/WORKFLOWS/architecture-review.md`; owner: `.ai/ROLES/architect.md`_
_Standards: documentation, coding, git_

## Objective

Produce a recorded architecture verdict (approve / request changes /
reject) for a proposed or realized architecture change, with explicit
checks against the manifest's technical vision and the drop-in contract.

## Required inputs

- The proposal (DECISIONS.md entry, NEXT_STEPS item, or milestone plan)
- `.ai/ARCHITECTURE.md` and `.ai/PROJECT_MANIFEST.md` (technical vision)
- Prior decisions (`.ai/DECISIONS.md`, append-only)
- Affected module list and alternatives considered

## Instructions (deterministic)

1. Read `.ai/PROJECT_MANIFEST.md` §3 (technical vision) and
   `.ai/ARCHITECTURE.md`.
2. Compare the proposal against ALL of these invariants; record pass/fail
   for each:
   - drop-in compatibility (public API surface unchanged without approval)
   - fail-open (optimization errors downgrade, never fail the request)
   - composable pipeline (stages swappable via `TokenOptConfig`)
   - no new runtime dependencies without approval
   - Python ≥ 3.10 compatibility
3. Determine gate status: if the change touches architecture, public API,
   package structure, storage schema, or deployment → user approval
   required; state this explicitly in the verdict.
4. Record the verdict with rationale, dated, in the session log; on
   approval update `.ai/ARCHITECTURE.md` and/or append to
   `.ai/DECISIONS.md`.
5. Hand off: approved proposals route to `implementation/feature.md` or
   `implementation/refactoring.md`.

## Expected outputs

- Verdict (approve / request changes / reject) with pass/fail per
  invariant
- Approval-gate statement (requires user approval: yes/no)
- Updated DECISIONS.md / ARCHITECTURE.md when approved

## Verification criteria

- [ ] Every invariant has an explicit pass/fail line
- [ ] Verdict recorded and dated
- [ ] No unapproved architecture change proceeded
- [ ] DECISIONS.md is append-only (nothing rewritten)

## Determinism rules

- Quote the exact document section that justifies each verdict line.
- Never approve "in principle" — approve against the invariants list.
