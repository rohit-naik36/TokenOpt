# Workflow: Documentation Update

_Owner: `.ai/ROLES/technical-writer.md`_
_Standards: documentation, ai-memory, git; related: `.ai/DOD.md`_

## Purpose

Keep documentation accurate and current — README, CHANGELOG, docstrings,
and `.ai/` memory — in the same commit as the change it describes, or as a
standalone correction when documentation drifts.

## Prerequisites

- A change with user-facing impact (code, config, behavior), or
- A documentation defect (stale README, broken link, missing docstring), or
- A release / milestone memory pass.

## Steps

1. **Identify surface** — which docs are affected: README, CHANGELOG,
   docstrings, `.ai/` state files, STANDARDS, GOVERNANCE_INDEX.
2. **Check facts** — verify claims against code; never document aspirational
   behavior (per M8.2 principle: documentation derives from reality).
3. **Update** — follow documentation-standard (module + public API
   docstrings mandatory; comments explain *why*, never *what*). Same
   commit as the code change when possible; standalone `docs:` commit for
   corrections.
4. **Cross-reference** — fix broken links; add links per
   `.ai/GOVERNANCE_INDEX.md` conventions.
5. **Changelog** — CHANGELOG.md entries under `[Unreleased]` (Added /
   Changed / Fixed) per release-standard.
6. **Memory** — update CURRENT_STATE / SESSION_LOG / NEXT_STEPS as
   applicable; flag stale memory as a defect (fix-bug).
7. **Commit + push** — `docs: <summary>` (git-standard); verify remote
   (Decision 11).

## Verification

- No broken relative links in changed docs.
- `ruff` clean (docstrings/lines) for any touched Python files.
- README claims verifiable against code (spot-check).

## Expected outputs

- Updated docs in the same commit as the code, or a `docs:` commit
- CHANGELOG entries
- Fresh `.ai/` memory

## Completion criteria

- [ ] Affected docs updated and accurate
- [ ] Changelog current
- [ ] Memory current
- [ ] Committed + pushed
