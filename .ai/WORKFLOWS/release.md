# Workflow: Release

_Owner: maintainer + `.ai/ROLES/architect.md`_
_Standards: release, git, testing, documentation, security_

## Trigger

The roadmap reaches a release milestone (e.g. M15) or a critical fix needs a
`PATCH` release.

## Steps

Follow `.ai/STANDARDS/release-standard.md` exactly:

1. **Freeze** — all DoD items complete; `main` green.
2. **Version bump** — `MAJOR.MINOR.PATCH` in `pyproject.toml` +
   `tokenopt/__init__.py` (keep in sync).
3. **Changelog** — finalize `Unreleased` → `vX.Y.Z` (Breaking/Added/Fixed/
   Changed/Removed).
4. **Verification gate** — clean checkout: pytest green, ruff clean, mypy
   clean (post-M1), `python -m build` + wheel smoke install.
5. **Tag & publish** — `git tag vX.Y.Z`, push tag (remote verified per
   Decision 11), GitHub release notes. PyPI publish = user approval only.
6. **Post-release** — update CURRENT_STATE (released version), checkpoint,
   SESSION_LOG entry.

## Exit criteria

- [ ] Tag `vX.Y.Z` visible: `git ls-remote --tags origin`
- [ ] Release notes published
- [ ] Memory updated + checkpoint created
- [ ] NEXT_STEPS updated with post-release items
