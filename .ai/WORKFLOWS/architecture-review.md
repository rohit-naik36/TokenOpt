# Workflow: Architecture Review

_Owner: `.ai/ROLES/architect.md`_
_Standards: documentation, coding, git; related: `.ai/DOD.md`_

## Purpose

Evaluate proposed or realized architecture changes against the manifest's
technical vision (drop-in compatibility, composable pipeline, fail-open)
before they are implemented or before a milestone closes. Produces a
recorded verdict in `DECISIONS.md` / `ARCHITECTURE.md`.

## Prerequisites

- A proposal exists: DECISIONS.md entry, NEXT_STEPS item, or a milestone
  with architectural impact.
- Architect has read `.ai/ARCHITECTURE.md` and the relevant proposal.

## Steps

1. **Collect** — gather the proposal, affected module list, and any
   alternative designs considered.
2. **Assess** — check against: manifest technical vision, drop-in contract,
   fail-open principle, extensibility, and dependency budget (no new
   dependencies without approval).
3. **Check gates** — any change to architecture, public API, package
   structure, storage schema, or deployment → user approval required
   before implementation proceeds.
4. **Decide** — record the verdict:
   - **Approve** — DECISIONS.md entry (or reaffirm), ARCHITECTURE.md updated.
   - **Request changes** — feedback recorded in the session; proposal back
     to owner.
   - **Reject** — reason recorded; alternative or deferral noted.
5. **Hand off** — approved proposals flow to implement-feature /
   refactoring workflows; the architect stays the review authority for the
   architecture-relevant diff.

## Verification

- DECISIONS.md entries are append-only and link the approving session.
- ARCHITECTURE.md reflects the current structure (no drift).
- No unapproved architecture changes exist in the diff.

## Expected outputs

- Verdict (approve / request changes / reject) with rationale
- Updated DECISIONS.md and/or ARCHITECTURE.md when approved
- Blocking items surfaced to the user

## Completion criteria

- [ ] Verdict recorded and dated
- [ ] Approval obtained before any gated change is implemented
- [ ] Docs reflect the decision
