# Checkpoint — M15: Release v0.1.0 to PyPI

_Date: 2026-08-02_

## Completed work

- **M15 — v0.1.0 released to PyPI** via Trusted Publishing (OIDC, Decision 26)
- PyPI Trusted Publisher configured by user: project `tokenopt` / owner
  `rohit-naik36` / workflow `publish.yml` — was `pending`, now `active`
- Annotated tag `v0.1.0` created and pushed → `.github/workflows/publish.yml`
  ran (build sdist+wheel, `twine check`, upload via
  `pypa/gh-action-pypi-publish`, `permissions: id-token: write`, no secrets)
- **Verified live**: `https://pypi.org/pypi/tokenopt/json` → 200, version 0.1.0
  (was 404 pre-publish on both PyPI and TestPyPI)
- Dependabot action-upgrade PRs (checkout/setup-python/upload-artifact → v7)
  already merged (`c914e1b`)
- Project memory updated: CURRENT_STATE, NEXT_STEPS, SESSION_STATE,
  TASK_QUEUE, ROADMAP, SESSION_LOG (Session 20 entry)

## Modified files (memory update, this session)

- `.ai/CURRENT_STATE.md`
- `.ai/NEXT_STEPS.md`
- `.ai/SESSION_STATE.md`
- `.ai/TASK_QUEUE.md`
- `.ai/ROADMAP.md`
- `.ai/SESSION_LOG.md`
- `.ai/CHECKPOINTS/CHECKPOINT_20260802_M15.md` (this file)

## Commit hashes

- Pre-session HEAD: `bc4ccbd` (docs: finalize v0.1.0 release notes and PyPI
  install instructions)
- Tag: `v0.1.0` (annotated, pushed to origin)
- Memory commit: (created after this checkpoint; see `git log -1`)

## Blockers

None. Trusted Publisher `active`; suite 167 green; coverage 94%; ruff clean;
mypy exit 0; twine check PASSED; CI green.

## Architecture decisions made

None new — M15 executed Decision 26 (Trusted Publishing) as planned.

## Next tasks

1. Commit memory + checkpoint (`docs:`), verify `git remote -v`, push to main.
2. Consume ADB backlog: High — ADB-03 (plugin architecture), ADB-11
   (internal architecture contracts); Medium — ADB-01/02/05/12/13.
3. Phase 2 roadmap features (router cost/latency tracking, cache file
   persistence, pluggable summarizer, real LLMLingua, local streaming,
   Prometheus exporter) per `.ai/NEXT_STEPS.md`.

## Exact prompt to continue work in a new session

> Read `.ai/PROJECT_MANIFEST.md`, `.ai/CURRENT_STATE.md`,
> `.ai/NEXT_STEPS.md`, `.ai/DECISIONS.md`, `.ai/ROADMAP.md`,
> `.ai/ARCHITECTURE.md`, `.ai/SESSION_LOG.md`, the most recent checkpoint
> in `.ai/CHECKPOINTS/`, `.ai/SESSION_STATE.md`, `.ai/TASK_QUEUE.md`, and
> `README.md`, in that order. Then continue from the ADB backlog (High:
> ADB-03 plugin architecture, ADB-11 internal architecture contracts) per
> `.ai/NEXT_STEPS.md` — record decisions in `.ai/DECISIONS.md` before
> implementing, follow `.ai/WORKFLOWS/implement-feature.md`, and keep all
> DoD gates green (pytest, ruff, mypy, build, twine check).
