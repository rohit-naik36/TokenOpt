# CHECKPOINT_20260801_M5

## Milestone: M5 — Continuous Integration

## Completed work
- `.github/workflows/ci.yml` — 3 jobs, fail-fast: `lint` (ruff+mypy, 3.12) →
  `test` (matrix 3.10/3.11/3.12, pytest + coverage ≥80% gate) →
  `package` (`python -m build` + fresh-venv wheel smoke + dist artifact).
  Triggers: push main / PR / workflow_dispatch; cancel-in-progress;
  least-privilege permissions.
- `CONTRIBUTING.md` — dev setup, DoD gates, CI layout + assumptions
  (floating versions, no optional extras in CI, offline tests, build
  CI-only), branch protection recommendations.
- README — CI badge + CI section.
- **CI executed and verified on GitHub: FULL MATRIX GREEN** (run
  30664914071 — lint ✅, test 3.10/3.11/3.12 ✅, package+smoke ✅).
- Workflow validated with actionlint 1.7.12 (zero findings) + PyYAML.

## Modified files
- `.github/workflows/ci.yml` (new)
- `CONTRIBUTING.md` (new)
- `README.md` (badge + CI section)
- `pyproject.toml` (mypy overrides: + `ollama.*`)
- `tokenopt/clients/local_client.py` (clear error when `ollama` missing)
- `tests/test_factory.py` (no optional-package dependency + 1 regression test)
- `.ai/` memory: DECISIONS (16), CURRENT_STATE, NEXT_STEPS, SESSION_LOG,
  SESSION_STATE, TASK_QUEUE, ROADMAP, this checkpoint

## Commits
- `10de3ea` ci: add GitHub Actions workflow with DoD gates
- `67b81dd` docs: document CI workflow and branch protection
- `ea306a2` fix: add ollama to mypy optional-extras overrides
- `a003026` fix: raise clear error for missing ollama package

## Remaining work
1. **M6** — release metadata: license (⚠ user choice), classifiers,
   CHANGELOG, build verification
2. M7 — pip-audit + secret scan + Dependabot (⚠ dev deps)
3. M8 — CONTRIBUTING extension, Makefile, examples
4. M10–M15 — governance docs, cleanup (⚠), refactor, arch docs,
   release v0.1.0 (⚠ PyPI optional)

## Blockers
- None for M5. **M6 has an approval gate** (license choice). M15 (PyPI)
  later. Open decision: RouterStage complexity-fallback hole (TASK_QUEUE).

## Decisions made
- **16** — `LocalClient` Ollama backend raises a clear actionable error when
  the optional `ollama` package is missing; mypy overrides extended to
  `ollama.*` (CI exposed two defects that the locally-installed `ollama`
  package was masking).

## Verification status
- pytest: 150 passed ✅ (coverage gate enforced)
- ruff: clean ✅
- mypy: exit 0 (20 files) ✅ (also in CI-equivalent venv without optionals)
- Coverage: 94% (gate ≥80%) ✅
- GitHub Actions: run 30664914071 — **all jobs green** ✅ (verified via API)

## Next prompt
"Approved. Begin Milestone 6 from .ai/IMPLEMENTATION_ROADMAP.md: release
metadata — I choose the <MIT/other> license; add license field + classifiers
to pyproject.toml, LICENSE file, CHANGELOG.md (Keep a Changelog), verify
python -m build + fresh-venv smoke, update memory, commit, verify git remote
-v (Decision 11), push, create checkpoint, wait for approval before M7."
