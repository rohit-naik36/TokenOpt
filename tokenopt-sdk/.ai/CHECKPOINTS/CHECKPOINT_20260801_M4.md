# CHECKPOINT_20260801_M4

## Milestone: M4 — Integration Tests & Coverage Gate

## Completed work
- `INTEGRATION_TEST_STRATEGY.md` (repo root) — integration-test definition,
  offline execution policy, provider isolation, determinism rules, gate
- `tests/integration/` — **19 tests, zero new dependencies** (Decision 15:
  `httpx.MockTransport` injected via `http_client=` kwarg):
  - `conftest.py` — OpenAI/Anthropic/500 transport handlers + request
    recording + client fixtures
  - `test_openai_flow.py` (8) — full drop-in flow (routing→compression→call→
    metrics), optimized body, cache-hit short-circuit, provider error
    re-raise + metrics, fail-open end-to-end, disabled-compression
    passthrough, metrics callback, factory
  - `test_anthropic_flow.py` (5) — messages flow, system split, gpt-rules
    filtered, custom claude rule, cache short-circuit, provider error
  - `test_local_client_flow.py` (5) — OpenAI-compatible backend, cache
    short-circuit, provider error, Ollama backend (fake module + transport),
    factory
- **2 genuine integration defects fixed (minimal, Decisions 13–14)**:
  1. `chat.completions.create` drop-in surface restored (openai + local
     adapters; was `chat.create` only → AttributeError on documented surface)
  2. Anthropic router scoped to claude-targeted rules (was routing requests
     to `gpt-4o-mini` → broken Anthropic API calls out of the box)
- **Coverage gate**: `[tool.coverage] fail_under = 80` + `--cov` addopts —
  enforced by pytest itself
- Coverage: suite 89% → **94%**; clients 88–94%

## Modified files
- `INTEGRATION_TEST_STRATEGY.md` (new)
- `tests/integration/conftest.py`, `test_openai_flow.py`,
  `test_anthropic_flow.py`, `test_local_client_flow.py` (new)
- `tokenopt/clients/openai_client.py` (chat nesting fix)
- `tokenopt/clients/local_client.py` (chat nesting fix)
- `tokenopt/clients/anthropic_client.py` (router scoping)
- `pyproject.toml` (`[tool.coverage]` + pytest `addopts`)
- `.ai/` memory: DECISIONS (13–15), CURRENT_STATE, NEXT_STEPS, SESSION_LOG,
  SESSION_STATE, TASK_QUEUE, ROADMAP, this checkpoint

## Commits
- (created after this checkpoint — see `git log --oneline -8`)

## Remaining work
1. **M5** — CI pipeline (GitHub Actions, Python 3.10–3.12 matrix) — no
   approval gate
2. M6 — license (⚠ user choice), CHANGELOG, metadata
3. M7 — pip-audit + secret scan + Dependabot (⚠ dev deps)
4. M8 — CONTRIBUTING, Makefile, examples
5. M10–M15 — governance docs, cleanup (⚠), refactor, arch docs,
   release v0.1.0 (⚠ PyPI optional)

## Blockers
- None for M4. M6 (license) and M15 (PyPI) are the remaining approval gates.
- Open decision (tracked in TASK_QUEUE): RouterStage complexity fallback
  rewrites models to `gpt-*` when custom rules exist but none match —
  shared by LocalClient/Anthropic custom-rule paths; deferred to avoid
  changing OpenAI routing behavior without approval.

## Decisions made
- **13** — Anthropic adapter scopes routing to claude-targeted rules only
  (mirrors Decision 8 LocalClient precedent)
- **14** — `chat` property nested exactly like the real SDK
  (`client.chat.completions.create`) — restores documented drop-in contract
- **15** — Integration tests use `httpx.MockTransport` via `http_client=`;
  M4 dev-dependency budget unspent (no new dependencies)

## Verification status
- pytest: 149 passed (19 new) ✅ — coverage gate enforced by pytest
- ruff: clean ✅
- mypy: exit 0 (20 files) ✅
- Coverage: 94% (gate ≥80%) ✅
- build: sdist + wheel OK ✅

## Next prompt
"Approved. Begin Milestone 5 from .ai/IMPLEMENTATION_ROADMAP.md: CI pipeline —
create .github/workflows/ci.yml with a Python 3.10/3.11/3.12 matrix running
ruff, mypy, pytest --cov (M4 gate), and python -m build + wheel smoke install;
verify the workflow syntax locally where possible; update memory; commit;
verify git remote -v (Decision 11); push; create checkpoint; wait for
approval before M6 (license choice)."
