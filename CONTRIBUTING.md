# Contributing to TokenOpt SDK

> Development-focused guide: setup, Definition of Done gates, CI pipeline and
> assumptions, and branch protection recommendations. A fuller onboarding
> guide (Makefile, examples, templates) is planned for milestone M8.

## Development setup

```bash
pip install -e ".[dev]"   # runtime deps + pytest, pytest-asyncio, pytest-cov, ruff, mypy
pytest tests/             # unit + integration suite (offline, deterministic)
```

## Definition of Done gates

Every commit must pass the five gates from `.ai/DOD.md`, in order:

1. `pytest tests/` — all green (includes the **≥80% coverage gate**,
   enforced by `[tool.coverage] fail_under = 80` in `pyproject.toml`)
2. `ruff check tokenopt tests` — zero findings
3. `mypy tokenopt` — exit 0
4. `python -m build` — sdist + wheel produced
5. Fresh venv: `pip install dist/*.whl` + `import tokenopt` smoke test

No silent waivers: a skipped gate requires explicit approval recorded in the
commit message and `.ai/SESSION_LOG.md`.

## Continuous Integration

`.github/workflows/ci.yml` runs every push to `main`, every pull request, and
on demand (`workflow_dispatch`). It is the single source of truth for release
readiness — if CI is red, the branch is not releasable.

### Pipeline layout

| Job | Runs | Gate(s) |
|-----|------|---------|
| `lint` | Python 3.12 (fast, version-independent) | ruff, mypy |
| `test` | **matrix** Python 3.10 / 3.11 / 3.12 | pytest + coverage ≥80% |
| `package` | Python 3.12, after `test` | `python -m build` + fresh-venv smoke |
| `security` | Python 3.12, after `lint` | `pip-audit` + `gitleaks` |

`lint` runs first so verification errors fail fast; `package` is last because
it depends on everything above. The test matrix uses `fail-fast: true` — one
failing Python version aborts the rest of the matrix immediately.

### Security checks

The `security` job enforces the baseline from `SECURITY.md`:

- `pip-audit --path .` — audits the **runtime** dependency set against the
  OSV advisory database; any known vulnerability fails the job (release
  blocker). The `tokenopt` package itself is skipped by the scanner (not on
  PyPI) and is expected.
- `gitleaks detect --log-opts=--all` (pinned 8.30.1) — scans full git history
  for secrets; any leak fails the job.

To reproduce locally:

```powershell
pip install -e ".[dev]"   # provides pip-audit
pip-audit --path . --desc
# gitleaks is a standalone binary; download from its GitHub releases and run:
gitleaks detect --source . --no-banner --log-opts=--all
```

Findings are classified release-blocker vs advisory in `SECURITY.md`.
Dependabot (`.github/dependabot.yml`) opens weekly PRs for `pip` dependencies
and GitHub Actions.

### Assumptions

- **Dependency versions float** within the ranges declared in `pyproject.toml`
  (pip cache via `actions/setup-python` keeps runs fast). A full lockfile is
  deferred to release hardening (M15).
- **Optional extras are not installed in CI** (`redis`, `sentence-transformers`,
  `llmlingua`, `ollama`) — tests exercise those paths fail-open with fakes.
- **Tests never touch the network** (`httpx.MockTransport`, see
  `INTEGRATION_TEST_STRATEGY.md`), so results are deterministic and CI-safe.
- The `build` package is installed in CI only and is **not** added to the
  project's dev extras (no new project dependencies).
- Runner: `ubuntu-latest`. Tests are OS-independent (no subprocesses, paths,
  or timing assertions), so results transfer to Windows/macOS.

### Watching a run

Push to `main` (or open a PR) and check
<https://github.com/rohit-naik36/TokenOpt/actions/workflows/ci.yml>.
The `tokenopt-dist` artifact (sdist + wheel) is uploaded from the `package`
job and retained for 7 days.

## Branch protection (recommendations only)

Org/repo settings are user-administered; these are the suggested rules for
`main`:

- Require status checks: **Lint (ruff + mypy)**, **Test (Python 3.10)**,
  **Test (Python 3.11)**, **Test (Python 3.12)**, **Package (build +
  fresh-venv smoke)** — all must pass before merging.
- Require branches to be up to date before merging (keeps CI deterministic).
- Do not allow bypassing the above settings.
- Optionally: require PR reviews and enforce linear history.
