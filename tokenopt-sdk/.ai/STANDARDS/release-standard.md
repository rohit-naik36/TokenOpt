# Release Standard

_Standard owner: `.ai/ROLES/architect.md` + maintainer_
_Related: `.ai/PROJECT_MANIFEST.md` §5, §10_

## Scope

Creating and publishing releases (`vX.Y.Z`).

## Process

1. **Freeze scope** — all Definition-of-Done items complete on `main`;
   CI green (after M5); coverage gate green.
2. **Version bump** — `MAJOR.MINOR.PATCH` per semver (see manifest §5):
   - `MAJOR` — breaking API changes (require approval; record deprecations)
   - `MINOR` — backward-compatible features
   - `PATCH` — backward-compatible fixes
   Update `tokenopt/__init__.py` `__version__` and `pyproject.toml` together.
3. **Changelog** — move `Unreleased` items under the new version with
   sections: Breaking / Added / Fixed / Changed / Removed.
4. **Verification gate** — on a clean checkout:
   - `pytest tests/` green
   - `ruff check tokenopt tests` clean
   - `mypy tokenopt` clean (after M1)
   - `python -m build` succeeds; wheel smoke-installed (`import tokenopt`)
5. **Tag & publish** — `git tag vX.Y.Z` on `main`; push tag (remote
   verified); GitHub release notes from the changelog. PyPI publishing is
   **user-approval only**.
6. **Post-release** — update `CURRENT_STATE.md` with the released version;
   create a checkpoint; record in `SESSION_LOG.md`.

## Release readiness checklist

- [ ] CI green (lint, types, tests, coverage, build)
- [ ] Changelog finalized
- [ ] Version consistent across `pyproject.toml` and `__init__.py`
- [ ] Remote verified before push
- [ ] Tag pushed and visible via `git ls-remote --tags`
- [ ] Memory updated + checkpoint created

## Pre-1.0 note

Under `0.x`, `MINOR` bumps may carry breaking changes **with explicit notice
in the changelog**; `PATCH` remains fix-only.
