# Git Standard

_Standard owner: `.ai/ROLES/reviewer.md`_
_Related: `.ai/PROJECT_MANIFEST.md` §5, Decision 11_

## Scope

Branching, commits, remotes, and history hygiene.

## Rules

1. **Branches** — `main` is the only permanent branch and must always be
   green. Feature work: short-lived `feat/<slug>` branches; fixes:
   `fix/<slug>`. No long-lived integration branches.
2. **Commit format** — `<type>: <summary>` with type in
   `feat | fix | refactor | docs | test | chore`; imperative mood; summary
   ≤ 72 chars. Example: `feat: add streaming support`.
3. **Small logical commits** — one change per commit; never one giant commit;
   never commit half-finished work.
4. **Commit gate** — commit only when all of: tests pass, lint passes, docs
   updated. (Type gate after M1.)
5. **Remote policy (Decision 11)** — never modify or guess the remote URL.
   Before **every** push: `git remote -v`; continue only if the URL matches
   `github.com/<username>/<repository>.git`; otherwise stop and ask.
6. **Push policy** — push after every completed milestone; never leave
   completed work only local. Confirm the push succeeded (branch up to date).
7. **Tags** — `vX.Y.Z` (semver) on `main` only, after the release
   verification gate (`.ai/STANDARDS/release-standard.md`).
8. **History hygiene** — no force-push to shared branches; no rewriting of
   pushed history; no merge noise (rebase for feature branches).
9. **Secrets** — never commit keys, `.env`, or credentials; they are
   gitignored and scanned (M7).
10. **Deletions** — file deletion requires approval (Approval Gates).

## Pre-push checklist

```bash
git status                 # clean or intentionally staged
git remote -v              # matches github.com/<user>/<repo>.git
pytest tests/ -q           # green
ruff check tokenopt tests  # clean
```

## Commit message examples

```
feat: add streaming passthrough to LocalClient
fix: use correct model for cache key in router stage
refactor: extract shared response usage helpers
docs: add extension guide to README
test: cover cache LRU eviction policy
chore: pin numpy for mypy compatibility
```
