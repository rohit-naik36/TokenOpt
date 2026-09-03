## Description

<!-- What does this change do? One paragraph max. -->

## Type of change

- [ ] feat — new capability
- [ ] fix — defect correction
- [ ] refactor — behavior-preserving structure change
- [ ] docs — documentation only
- [ ] test — test coverage change
- [ ] chore — maintenance (memory, tooling)

## Checklist (done-gate, `.ai/DOD.md`)

- [ ] SDK behavior unchanged unless the PR intent says otherwise (drop-in contract preserved)
- [ ] `pytest tests/` — all green (158+)
- [ ] `ruff check tokenopt tests` — clean
- [ ] `mypy tokenopt` — clean
- [ ] Decision recorded in `.ai/DECISIONS.md` if this changes architecture or public API (approval gate)
- [ ] Memory updated (CURRENT_STATE / SESSION_LOG / NEXT_STEPS as applicable)
- [ ] Single-maintainer repo: this PR is prepared to merge directly after CI passes

## Evidence

<!-- Commands run, coverage %, CI badge, links to reproduction. -->

## Release note (if user-facing)

<!-- One line for CHANGELOG.md. -->
