# Prompt: Release Preparation

_Group: operations_
_Related: `.ai/WORKFLOWS/release.md`; owner: `.ai/ROLES/release-manager.md`_
_Standards: release, git, testing, security; inputs from: uat-execution, regression-verification_

## Objective

Prepare a verified, documented `vX.Y.Z` release deterministically — freeze,
bump, changelog, full gate, tag, notes — with PyPI publish strictly gated
on user approval.

## Required inputs

- Green `main` + milestone scope (what ships in this release)
- QA verdicts (uat-execution, regression-verification), scanner results
  (pip-audit, gitleaks), DoD sign-off
- `[Unreleased]` CHANGELOG content

## Instructions (deterministic)

1. Freeze scope: confirm every DoD item complete and `main` green; no new
   commits after freeze without user approval.
2. Confirm pre-release checks: UAT + regression verdicts pass; scanners
   clean (`pip-audit --path .`, `gitleaks detect --log-opts=--all`).
3. Determine the bump: MAJOR (breaking, approval), MINOR (features),
   PATCH (fixes) per semver and manifest §5.
4. Bump version in BOTH `pyproject.toml` and `tokenopt/__init__.py`
   (must match); verify with `importlib.metadata.version("tokenopt")`.
5. Finalize CHANGELOG: `[Unreleased]` → `vX.Y.Z` with Breaking/Added/
   Fixed/Changed/Removed groups per release-standard.
6. Run the release gate on a clean checkout:
   ```bash
   pytest tests/ -q
   ruff check tokenopt tests
   mypy tokenopt
   python -m build
   twine check dist/*
   ```
7. Tag `vX.Y.Z` on `main`; push tag after verifying `git remote -v`
   (Decision 11); publish GitHub release notes.
8. PyPI publish ONLY with explicit user approval.
9. Post-release: update `.ai/CURRENT_STATE.md` (released version),
   create checkpoint, update `.ai/NEXT_STEPS.md` with post-release items.

## Expected outputs

- Tag + release notes; version consistent across pyproject/`__init__`/
  CHANGELOG
- Post-release memory + checkpoint

## Verification criteria

- [ ] `git ls-remote --tags origin` shows `vX.Y.Z`
- [ ] Release gate green (all 5 commands)
- [ ] Version triple consistency verified
- [ ] QA + security verdicts attached
- [ ] PyPI untouched without user approval

## Determinism rules

- The release gate runs on the tagged commit, never on working-tree state.
- No emergency exceptions to the gate without user approval.
