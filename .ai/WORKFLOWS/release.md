# Workflow: Release

_Owner: `.ai/ROLES/release-manager.md`; arch review: `.ai/ROLES/architect.md`_
_Standards: release, git, testing, documentation, security_
_Related: uat-execution, regression-verification; `.ai/DOD.md`_

## Purpose

Produce a verified, tagged, documented release (`vX.Y.Z`) deterministically,
per `release-standard.md` — with publishing to PyPI gated on user approval.

## Prerequisites

- Release milestone reached (e.g. M15) or a critical fix needs a `PATCH`
  release.
- All DoD items complete; `main` green; UAT + regression executed (or
  explicitly waived by the user for a hotfix).

## Steps

1. **Freeze** — all DoD items complete; `main` green; scope locked.
2. **Pre-release checks** — UAT execution + regression verification
   workflows pass; scanner results clean (pip-audit, gitleaks).
3. **Version bump** — `MAJOR.MINOR.PATCH` in `pyproject.toml` +
   `tokenopt/__init__.py` (keep in sync).
4. **Changelog** — finalize `[Unreleased]` → `vX.Y.Z` (Breaking/Added/
   Fixed/Changed/Removed per release-standard).
5. **Verification gate** — clean checkout: pytest green, ruff clean, mypy
   clean, `python -m build` + `twine check` + wheel smoke install.
6. **Tag & publish** — `git tag vX.Y.Z`, push tag (remote verified per
   Decision 11), GitHub release notes. **PyPI publish = user approval
   only.**
7. **Post-release** — update CURRENT_STATE (released version), checkpoint,
   SESSION_LOG entry; NEXT_STEPS updated with post-release items.

## Verification

```bash
pytest tests/ -q
ruff check tokenopt tests
mypy tokenopt
python -m build
twine check dist/*      # when publishing
```

## Expected outputs

- Tag `vX.Y.Z` on `main` + release notes
- Consistent version in pyproject + `__init__.py` + CHANGELOG
- Post-release memory + checkpoint

## Completion criteria

- [ ] Tag visible: `git ls-remote --tags origin`
- [ ] Release notes published
- [ ] Memory updated + checkpoint created
- [ ] NEXT_STEPS updated with post-release items
