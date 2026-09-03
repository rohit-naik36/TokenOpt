# Session Log

## 2026-08-01 — Session 17: Pre-M13 Routing Precedence Decision

### Work performed
- **Reviewed RouterStage** (`.ai/ROUTING_PRECEDENCE_REVIEW.md`): findings
  F1 (rule provenance), F2 (explicit-model detection), F3 (provider
  clients), F4 (empty-query path), F5 (fail-open), F6 (routing_reason).
- **Implemented Decision 24 — five-level precedence (least surprise)**:
  1. explicit caller model never overridden
  2. matching rule wins by priority
  3. custom rules exist but none match → **preserve caller's model**
  4. no custom routing configuration → built-in complexity routing
  5. provider default (resolved model stands)
- **Code**: `RoutingRule.builtin` (default rules marked; only user rules
  count as "custom"); `OptimizationContext.model_explicit` +
  `OptimizationPipeline.run(model_explicit=...)` +
  `chat_completion(model_explicit=...)` (additive, backward compatible);
  RouterStage records `routing_precedence` on every path and no longer
  overwrites on empty query; `_record_metrics` maps
  `routing_reason` + `routing_precedence`; `RequestMetrics` gains
  `routing_precedence` (additive); `LocalClient.chat_completion`
  pass-through. **Fixed**: custom rules no-match on Anthropic/local no
  longer rewrites to `gpt-*` (invalid model → would break the call).
- **Tests**: test_router.py (empty-query tests → preserve contract;
  all-rules-failing → preserve; +5 new: explicit-over-rule,
  explicit-over-complexity, explicit-without-query, custom no-match
  preserve, builtin-only complexity, mixed preserve); metrics_clarity
  (rule-match + complexity tests use implicit model; +2 new: preserved
  reason, explicit never overridden); anthropic_flow (custom-rule test
  implicit; +1 new: no-match preserves explicit claude model); openai_flow
  (full-flow test implicit so the routing counter is exercised). Suite
  **167 passed** (was 158).
- **Examples**: pipeline_config.py reworked — math→o1-mini (rule),
  code→gpt-4o (rule), simple/complex→preserved gpt-4o-mini, plus a
  no-custom-rules config showing complexity (high)→gpt-4o, plus OFF vs ON;
  `_format.py explain()` prints "Routing kept X (preserved (no rule
  matched))" for non-applied routing. **Validated against the stub server:
  all 6 examples exit 0 and output matches docstrings** (M8.2 truthfulness
  rule).
- **Docs**: ARCHITECTURE.md routing precedence section; README precedence
  list; CHANGELOG entry (Added routing_precedence + Changed precedence).
- **Commits**: (see checkpoint — feat: precedence contract, test:
  router contract, test: integration, docs: review/decision, docs:
  examples, chore: memory).

## 2026-08-01 — Session 16: M12 — Repository Curation

### Work performed
- **Inventoried the repository** (root + sub-trees) and classified every
  entry: active governance / generated artifact / duplicate / historical
  archive / future reference / user-owned — `.ai/REPOSITORY_INVENTORY.md`.
- **Deleted (approved scope: duplicates + regenerated only)**:
  - 7 empty artifact dirs: `C?ProjectsNew/`, `Idea_Factory/`,
    `Projecttests/`, `Projecttokenoptclients/`,
    `Projecttokenoptobservability/`, `Projecttokenoptpipeline/`,
    `Projecttokenoptutils/`
  - generated artifacts: `dist/`, `tokenopt.egg-info/`, `.coverage`,
    `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, 8× `__pycache__/`
- **Archived**: `SESSION_BACKUP.md` → `.ai/ARCHIVE/` via `git mv`
  (history intact; audit finding 9 closed).
- **Created `.ai/REPOSITORY_RETENTION_POLICY.md`**: five categories
  (permanent / archived / regenerated / disposable / user-owned) + rules
  (deletion gate, append-only `.ai/`, archive-not-delete, curation
  procedure, disposition log).
- **Added GitHub templates**: `PULL_REQUEST_TEMPLATE.md`,
  `ISSUE_TEMPLATE/bug_report.md`, `ISSUE_TEMPLATE/feature_request.md`,
  `CODEOWNERS` (single-maintainer posture → `@rohit-naik36`).
- **Updated governance**: REPOSITORY_AUDIT.md §7 dated closure (findings
  6 + 9 and plan item 8 closed, evidence-based); GOVERNANCE_INDEX gains
  Policies section (2 policies, owner = repository-auditor);
  repository-audit workflow gains a curation step + retention-policy
  prerequisite.
- **Kept**: `docs/UAT.md` (active governance — referenced by qa-engineer
  role + uat-execution workflow), all `.ai/` memory, `TEST.txt`
  (user-owned scratch, untouched).
- **Verification**: link check 79/79 resolve; git history intact (85
  commits, `SESSION_BACKUP.md` rename detected); root tree now only
  intentional entries; suite **158 passed**; ruff/mypy clean; SDK/tests/
  examples untouched.
- **Commits**: (see checkpoint — logical commits: retention docs,
  curation, templates, governance closure, memory).

## 2026-08-01 — Session 15: M11 — AI Prompt Library

### Work performed
- **`.ai/PROMPTS/` created, grouped by purpose** (4 groups, 10 prompts):
  - `design/` — architecture-review
  - `implementation/` — feature, bug-fix, refactoring, unit-testing
  - `verification/` — integration-testing, regression-verification
  - `operations/` — documentation-update, release-preparation,
    repository-audit
- **Every prompt follows the fixed template**: objective, required
  inputs, deterministic numbered instructions (exact commands like
  `pytest tests/ -q` and full relative paths), expected outputs,
  verification criteria (executable checkboxes), determinism rules
  (never/always constraints, e.g. "reproduction test before fix",
  "evidence over memory", "fail-open preserved").
- **`.ai/PROMPTS/README.md`** — prompt design guidelines: grouping table,
  template spec, determinism rules, the four-layer model (prompt =
  execution / workflow = runbook / role = ownership / standard =
  normative rule), add + maintenance rules (append-only; a prompt is
  "live" only after real-task use or user acceptance).
- **Cross-references**: GOVERNANCE_INDEX gains a Prompts table (10 rows:
  prompt → group → owner role → governing workflow); each prompt links
  its workflow + owner role + standards; IMPLEMENTATION_ROADMAP M11
  marked DONE with executed scope; ROADMAP M11 line added; DECISIONS +22.
- **Verification**: link check over 75 md files (all relative links
  resolve); prompt→workflow/role cross-refs 10/10 resolve; gates green
  (158 passed, ruff clean, mypy exit 0); SDK/tests/examples untouched
  (docs-only milestone).
- **Commits**: (see checkpoint — logical commits: prompts by group,
  guidelines, cross-refs, memory).

## 2026-08-01 — Session 14: M10 — AI Engineering Governance Expansion

### Work performed
- **Phase 1 review** — audited WORKFLOWS (5), ROLES (4), STANDARDS (8),
  AGENTS.md, manifest, roadmaps, checkpoints. 8 inconsistencies fixed
  (I1–I8): stale "(mypy after M1 fix)"; divergent verification blocks;
  release.md owner "maintainer" (no such role); fix-bug missing checkpoint
  standard; no DOD links; ROADMAP counts; IMPLEMENTATION_ROADMAP M10
  pre-execution scope; no registry. Found no blocking duplication
  (self-contained runbooks accepted as an agent feature).
- **WORKFLOWS 5 → 14** — unified template (Purpose / Prerequisites /
  Steps / Verification / Expected outputs / Completion criteria). New:
  refactoring, architecture-review, documentation-update,
  dependency-upgrade, security-response, performance-investigation,
  uat-execution, regression-verification, repository-audit. Existing 5
  rewritten in place (content preserved; gates standardized to
  pytest + ruff + mypy; DOD linked).
- **ROLES 4 → 11** — extended template (Authority / Required inputs /
  Expected outputs / Success criteria added). New: product-strategist,
  product-manager, qa-engineer, security-reviewer, release-manager,
  devops-engineer, repository-auditor. Existing 4 extended. Single-owner
  matrix prevents overlap (reviewer vs qa vs security scoped explicitly).
- **`.ai/GOVERNANCE_INDEX.md`** — machine-consumable registry: 11 roles,
  14 workflows, 8 standards, ownership matrix, single approval gate, ASCII
  handoff map (Idea → Software Factory substrate).
- **`.ai/GOVERNANCE_REVIEW.md`** — findings table (I1–I8), multi-agent
  validation matrix (no circularity, no conflicting ownership, no missing
  gates, deterministic order, clear handoffs), rationale.
- **Reference updates** — AGENTS.md WORKFLOWS/ROLES lines point to the
  index; ROADMAP Phase 0 counts + M10 done (removed a fabricated "M9 done"
  line — M9 was never executed separately, marked "covered by M0.1" in the
  implementation roadmap instead); DECISIONS +21.
- **Verification** — link check: all relative links in 64 md files
  resolve; all 14 workflow owners map to real role files; gates green
  (158 passed, ruff clean, mypy exit 0); SDK/tests/examples/README
  untouched (docs-only milestone).
- **Commits**: `72ddef0` (9 workflows), `76a83b4` (template unification),
  `588d182` (7 roles), `e49d6c1` (role extensions), `2cf461f` (index +
  review), `104d366` (references); memory commit follows; pushed; CI green.

## 2026-08-01 — Session 13: M8.2 Value Demonstration & Showcase

### Work performed
- **`RequestMetrics.routing_reason`** (additive field): populated in
  `base._record_metrics` from `ctx.metrics` — matched rule name, else
  `complexity-based (low|medium|high)`; RouterStage (`routing_rule` /
  `routing_complexity` keys) remains the single source of truth.
- **examples/_format.py**: `explain(metrics)` prints "Why:" lines derived
  only from recorded metrics; `print_comparison(title, before, after)`
  prints OFF vs ON side-by-side.
- **6 examples rewritten as value demonstrations** — header docstrings
  ("Demonstrates / Expected outcome"), realistic long prompts:
  - quickstart: drop-in + compression + routing reason (default rules)
  - openai_basic: compression OFF (331→331) vs ON (331→184, ~44%), then
    cache miss→hit on a separate cached client
  - anthropic_basic: 5-turn conversation with threshold 150 →
    summarization applied (167→140)
  - local_basic: multi-paragraph code-review prompt (164→89, ~46%) +
    miss→hit; cloud routing rules auto-skipped for local backends
  - pipeline_config: 4 prompts → 4 routing decisions (simple→gpt-4o-mini
    low, code→gpt-4o medium, math→o1-mini math_tasks rule, complex→gpt-4o
    high) + routing OFF vs ON comparison
  - metrics_observability: field-by-field annotation, latency-split story
    (miss 157.8 ms overhead vs hit 0.3 ms), callback, utilities
- **README/CHANGELOG**: example sections describe demonstrated value;
  `[Unreleased]` gains Added (routing_reason) + Changed (examples/README).
- **Regression tests** (+3 in test_metrics_clarity.py): routing_reason =
  rule name on match / complexity fallback string / empty when routing off.
- **Validation (clean env)**: fresh venv (m82-env) + stub server at
  127.0.0.1:8787 — all 6 examples exit 0; every printed "Why:" line
  cross-checked against the actual metrics — truthful.
- **Truthfulness fixes en route**: quickstart prompt removed "I think"
  (default `reasoning_tasks` rule matches substring "think" → o1-mini;
  demo now shows complexity fallback instead); openai_basic header claim
  corrected to measured ~44%; em-dashes in console output → ASCII "-"
  (Windows console rendered them as �).
- **Commits**: `203b3d4` feat: routing_reason; `ec4f638` docs: examples;
  `2a6093f` docs: README + CHANGELOG; pushed to main.
- **Gates**: 158 passed (94%), ruff clean (incl. examples), mypy exit 0,
  build + twine PASSED.

## 2026-08-01 — Session 12: Post-M8 UAT Refinements

### Work performed
- **Metrics clarity (SDK, additive — no API break)**: `RequestMetrics` gains
  `compression_attempted` / `compression_effective` / `tokens_saved` /
  `reduction_percentage` + `model_latency_ms` (inference = total - overhead),
  populated in `base._record_metrics`; structured JSON log enriched with the
  same fields (production logging preserved). `compression_applied` kept
  for backward compatibility (now documented as "stage ran").
- **Example output (UX)**: new `examples/_format.py` — `quiet()`
  (suppresses INFO JSON via `logging.disable(INFO)` + tokenopt level),
  `print_request()` (Model, Cache hit, Compression attempted/effective,
  Tokens, Latency total|model|TokenOpt overhead, Estimated cost, Response),
  `print_summary()`. All 6 examples rewritten to use it; local_basic now
  demonstrates miss→hit with two identical requests + per-instance cache
  note; examples gained short explanatory comments.
- **README**: "5-Minute Quick Start" (7 steps + expected output) near top.
- **docs/UAT.md**: permanent manual acceptance checklist — 10 scenario
  groups (env, install, quick start, OpenAI, Anthropic, Local/Ollama,
  cache, routing, metrics, error handling, clean uninstall) + sign-off.
- **Regression tests** (`tests/integration/test_metrics_clarity.py`, 5):
  short prompt = attempted-but-not-effective; long prompt = effective with
  tokens_saved>0; latency split total = model + overhead; cache-hit records
  clarified fields; disabled compression = not attempted.
- **CHANGELOG [Unreleased]**: Changed entries for metrics + examples + UAT.
- **Validation (clean env)**: fresh venv + `pip install -e .` + stub server
  — all 6 examples exit 0 with clean readable output; routing (gpt-4o-mini/
  gpt-4o/o1-mini), cache miss→hit, anthropic, callback all verified.
- **Defect fixed en route**: my own `_format.py` edit corrupted a print
  statement (SyntaxError) — caught by validation, fixed immediately.
- **Gates**: 155 passed (94%), ruff clean (incl. examples), mypy exit 0,
  build + twine PASSED, CI badge passing.

## 2026-08-01 — Session 11: M8 — Developer Onboarding & Experience

### Work performed
- **examples/** (6 runnable scripts, ruff-clean):
  `quickstart.py`, `openai_basic.py` (2nd call demonstrates cache hit),
  `anthropic_basic.py`, `local_basic.py` (env-overridable endpoint),
  `pipeline_config.py` (custom routing rules + complexity fallback),
  `metrics_observability.py` (callback + cost + token utils)
- **README rewritten** — Quick Start, Installation (⚠ not on PyPI yet →
  git install; core + 7 extras table), provider examples, factory, config,
  project structure tree, Troubleshooting/FAQ (9 entries), dev/CI/security,
  status, license. FAQ claims verified against stage code.
- **Makefile** — help/install/dev/lint/typecheck/test/coverage/build/audit/
  smoke/clean, mirroring CI.
- **CONTRIBUTING.md** — dropped "M8 planned" note; documents Makefile,
  examples, env vars.
- **Validation on clean environment** (fresh venv, `pip install -e .`):
  - All 6 examples executed against a local OpenAI/Anthropic-compatible
    stub server (temp, not committed) — exit 0; routing (gpt-4o-mini/gpt-4o/
    o1-mini), cache hit, anthropic messages API, local flow, callback all
    verified end-to-end
  - `pip install git+https://github.com/rohit-naik36/TokenOpt.git` dry-run ✅
  - All 5 extras (`[cache] [local] [semantic] [compression] [all]`) resolve
    via `pip install --dry-run` ✅
- **Doc-discovered defect fixed**: `metrics_observability.py` forward-ref
  `"RequestMetrics"` flagged F821 — replaced with a real import (public API
  unchanged).
- **Gates**: 150 passed (94%), ruff clean (incl. examples), mypy exit 0,
  build + twine check PASSED.

## 2026-08-01 — Session 10: M7 — Security Baseline

### Work performed
- **Prerequisite (user instruction)**: author metadata personalized from
  GitHub handle to **Rohit Naik** — `pyproject.toml` `authors` + LICENSE
  copyright line. Repo ownership/URLs untouched. Verified in built wheel:
  `Author: Rohit Naik`, `License: MIT`.
- **pip-audit** — added `pip-audit>=2.7.0` to the `dev` extra (approved);
  local scan `pip-audit --path . --desc` (2.10.1): **zero vulnerabilities**
  (tokenopt itself skipped — not on PyPI, expected).
- **gitleaks** — not a pip package (Go binary): pinned release **8.30.1**
  downloaded in CI via curl; local full-history scan
  `gitleaks detect --log-opts=--all`: **58 commits scanned, no leaks**.
- **CI** — new `security` job (after `lint`): pip-audit + gitleaks, both
  blocking; run 30666354747 fully green (lint, security, test ×3, package).
- **Dependabot** — `.github/dependabot.yml`: weekly `pip` + `github-actions`
  updates, `numpy>=2.5` ignored (breaks Python 3.10 + mypy), limit 5 PRs.
  It activated immediately and opened 3 action-upgrade PRs
  (checkout/setup-python/upload-artifact → v7) — advisory, user to merge.
- **SECURITY.md** — supported versions (0.1.x ✅, <0.1.0 ❌, main dev),
  private reporting (GitHub Security Advisories + email fallback, 7/14-day
  timelines), security scope (package, runtime deps, committed secrets, CI
  config; user-side keys/optional extras out of scope), coordinated
  disclosure (90-day / immediate on public exploit, no bounty),
  **release-blocker vs advisory classification table** with CI behavior.
- **CONTRIBUTING.md** — security job row in pipeline table + "Security
  checks" section with local reproduction commands.
- **No SDK functionality changed** — tooling, CI, and docs only.

## 2026-08-01 — Session 9: M6 — Release Metadata (MIT)

### Work performed
- **LICENSE** — MIT (user decision), Copyright (c) 2026 rohit-naik36.
- **CHANGELOG.md** — Keep a Changelog format + SemVer; `[Unreleased]` +
  `[0.1.0] - 2026-08-01` (Added: all core functionality, observability,
  factory, CI, 150 tests; Fixed: the 8 defects found during M1–M5).
- **pyproject.toml metadata** (Decision 17) — `authors = [rohit-naik36]`,
  enriched description, 12 keywords, 9 classifiers (Alpha; Python
  3.10–3.12; OS Independent; AI/ML topics), `[project.urls]`
  (Homepage/Repository/Issues/Documentation/CI — cross-checked against
  `git remote -v`), PEP 639 `license = "MIT"` (SPDX expression) with build
  floor bumped to `setuptools>=77` (latest is 83.x; legacy license
  classifier is rejected by setuptools 83 — removed it after build error).
- **README release-readiness review** — added "Supported providers &
  features" table (OpenAI gpt-*/o1-*/o3-*, Anthropic claude-*, Local
  Ollama/vLLM/llama.cpp/LM Studio), "Optional extras" mapping, "Status"
  (pre-1.0, fails open), License → MIT.
- **Packaging verification** — `python -m build` ✅ (sdist + wheel);
  `twine check` **PASSED** for both ✅; fresh-venv wheel install +
  `import tokenopt` ✅; installed metadata via `importlib.metadata`:
  version 0.1.0 (matches `tokenopt.__version__`), License-Expression MIT,
  9 classifiers, 5 project URLs, 6 runtime deps + extras; sdist ships
  LICENSE + README.
- **No runtime functionality changed** (metadata/docs only).
- **Verification (all green)**: `pytest tests/` **150 passed**; ruff clean;
  `mypy tokenopt` exit 0; coverage **94%**.
- **STOPPING — awaiting approval to begin M7** (security hardening;
  ⚠ new dev deps: pip-audit, gitleaks, Dependabot).

## 2026-08-01 — Session 8: M5 — Continuous Integration

### Work performed
- **`.github/workflows/ci.yml`** — CI pipeline as the single source of truth
  for release readiness. Triggers: push to `main`, PRs, `workflow_dispatch`.
  `concurrency` cancel-in-progress; `permissions: contents: read`; job
  timeouts. Three jobs, fail-fast ordering (`lint` → `test` → `package`):
  1. `lint` (Python 3.12) — `pip install -e . ruff mypy` →
     `ruff check tokenopt tests` → `mypy tokenopt`
  2. `test` — matrix **3.10/3.11/3.12** → `pip install -e ".[dev]"` →
     `pytest tests/` (coverage ≥80% gate from M4 enforced in CI)
  3. `package` (3.12, after test) — `pip install build` → `python -m build`
     → fresh-venv wheel install + `import tokenopt` smoke (DoD gate 5) →
     dist artifact upload (7-day retention)
- **`CONTRIBUTING.md`** (new) — dev setup, DoD gates, CI pipeline layout,
  assumptions (floating versions + pip cache; optional extras not installed
  in CI; offline/deterministic tests; `build` package CI-only), branch
  protection recommendations (user-administered: required status checks,
  up-to-date branches, no bypass).
- **README** — CI badge + "Continuous Integration" section.
- **Workflow validation**: PyYAML parse + **actionlint 1.7.12** (zero
  findings) before push.
- **CI execution — first run FAILED on lint** (exactly what CI is for):
  `mypy tokenopt` flagged `import ollama` (local_client.py:52) as
  import-not-found. Root cause: `ollama` is installed in the local env, so
  local mypy resolved it — the M1 mypy-overrides fix missed `ollama.*`.
  Fixed: added `"ollama.*"` to the optional-extras overrides in
  `pyproject.toml` (consistent with the M1 precedent comment).
- **CI execution — second run FAILED on Test (3.12)** (fail-fast cancelled
  3.10/3.11): `tests/test_factory.py` constructed `LocalClient` with the
  default Ollama URL → bare `ModuleNotFoundError: No module named 'ollama'`
  (again masked locally by the installed package). Fixed:
  - `local_client.py` `_create_client` now wraps `import ollama` and raises a
    clear `RuntimeError` with a `pip install tokenopt[local]` hint
    (Decision 16; aligns with fail-open/optional-extras philosophy)
  - `tests/test_factory.py`: the two local-client tests now pass an
    OpenAI-compatible `base_url` (no optional package needed); added
    regression test for the missing-package error (deterministic via
    `monkeypatch.setitem(sys.modules, "ollama", None)`)
- **CI execution — third run: FULL GREEN** (run 30664914071): Lint ✅,
  Test 3.10/3.11/3.12 ✅, Package + fresh-venv smoke ✅. Verified via the
  public GitHub API (repo is public; job-log download needs admin, so
  failures were reproduced locally in CI-equivalent temp venvs instead).
- **Verification (all green)**: `pytest tests/` **150 passed** (149 + 1
  regression test); ruff clean; `mypy tokenopt` exit 0 (also in the
  CI-equivalent venv without optional packages); coverage **94%**.
- **STOPPING — awaiting approval to begin M6** (license choice).

## 2026-08-01 — Session 7: M4 — Integration Tests & Coverage Gate

### Work performed
- **`INTEGRATION_TEST_STRATEGY.md`** (repo root) — integration-test
  definition (≥2 layers through a public entry point), offline execution
  policy, provider isolation mechanics, determinism rules, coverage gate.
- **`tests/integration/` — 19 tests, zero new dependencies** (Decision 15):
  - `conftest.py` — `httpx.MockTransport` handlers for OpenAI/Anthropic
    payloads + HTTP 500, request-body recording fixtures, client fixtures.
  - `test_openai_flow.py` (8) — full drop-in flow (route → compress →
    call → metrics; body model gpt-4o-mini + routing counter), optimized
    request body (filler removed, truncated, code-routed to gpt-4o),
    cache-hit short-circuit (2 identical calls → 1 provider request,
    cache_hit_rate 0.5), provider 500 → `openai.APIStatusError` + error
    metrics, BoomStage fail-open end-to-end, disabled compression
    passthrough, metrics callback receives `RequestMetrics`, factory
    roundtrip.
  - `test_anthropic_flow.py` (5) — full messages flow (model/max_tokens
    passthrough, no routing), system split into `system` param +
    `max_tokens` 4096 default, gpt-targeted default rules filtered out,
    custom claude routing rule applied, cache short-circuit, provider
    error metrics.
  - `test_local_client_flow.py` (5) — OpenAI-compatible backend full flow
    (model/messages passthrough), cache short-circuit, provider error,
    Ollama backend end-to-end via fake `ollama` module (transport-level
    HTTP, `_normalize_ollama_response` + metrics), factory roundtrip.
- **2 genuine integration defects found + fixed (minimal):**
  1. **Drop-in `chat.completions.create` surface broken** (Decision 14) —
     the `chat` property exposed `chat.create(...)` only; the documented
     surface (`README`, package docstring) raised `AttributeError`.
     Fixed in `openai_client.py` + `local_client.py` to mirror the real
     SDK nesting (`chat.completions.create`).
  2. **Anthropic adapter broken out of the box** (Decision 13) — default
     config routed requests to `gpt-4o-mini` (complexity fallback), sending
     a nonexistent model to the Anthropic API. Fixed: `_build_pipeline`
     drops the default router and keeps only claude-targeted rules,
     mirroring the LocalClient precedent (Decision 8).
- **Coverage gate** — `[tool.coverage] fail_under = 80` +
  `addopts = "--cov=tokenopt --cov-report=term-missing"` in
  `pyproject.toml`; enforced on every pytest run.
- **Verification (all green)**: `pytest tests/` **149 passed** (130 existing
  untouched + 19 new); ruff clean; `mypy tokenopt` exit 0; `python -m build`
  sdist + wheel.
- **Coverage**: suite 89% → **94%** (gate: ≥80%). Clients now 88–94%
  (openai 92, anthropic 91, local 94, base 88).
- **STOPPING — awaiting approval to begin M5** (CI; no approval gate).

## 2026-08-01 — Session 6: M3 — Pipeline Stage Tests 2 (cache, RAG, few-shot)

### Work performed
- **Wrote 53 behavioral-contract tests** (network-free, public-contract only,
  scripted embedding providers for determinism):
  - `tests/test_cache.py` (18) — miss metadata + metric; store/exact-hit
    roundtrip; stats/hit counts; LRU eviction at `cache_max_size`;
    TTL expiry (exact and semantic paths); semantic hit/miss at
    `cache_similarity_threshold`; model-mismatch no-hit; Redis roundtrip +
    Redis-failure fail-open (fake clients, no network); `clear()` (memory +
    Redis); non-string content; determinism; no mutation.
  - `tests/test_rag_optimizer.py` (15) — `context:`/`retrieved:` line
    extraction + `rag_chunks` structured key; relevance ranking, threshold
    filtering, `rag_max_chunks` cap; dedup near-duplicates; no-context and
    no-query no-ops; malformed content skipped; determinism; no mutation.
  - `tests/test_fewshot.py` (13) — similarity/diversity/random strategies;
    max-examples caps and fewer-than-max; default config (similarity, cap 3);
    injection order/format (user/assistant pairs after system); example
    without output; metrics; determinism; no mutation.
  - `tests/test_pipeline_config.py` (+7) — cache enable/disable gating; RAG
    and few-shot always-on by default; pipeline fail-open.
- **4 defects found + fixed (minimal, no API change):**
  1. **Cache key collision** — non-string message content (e.g. multimodal
     lists) was skipped in `_make_cache_key`/`_messages_to_text`, so all such
     prompts hashed to the same key and could serve each other's cached
     responses. Fixed: serialize via `json.dumps(sort_keys=True)`.
  2. **RAG dedup embedding misalignment** — `_optimize_chunks` re-sorted
     chunks by relevance but passed `chunk_embeddings[:len(filtered)]`
     (original order) to `_deduplicate_chunks`, comparing each chunk against
     the wrong embedding; valid chunks could be dropped as "duplicates".
     Fixed: embeddings carried through the sort in the scored tuples.
  3. **Few-shot injection dropped without system message** — `fewshot_applied`
     was set but nothing injected. Fixed: examples prepended when no system
     message exists.
  4. **Pipeline fail-open missing** — `OptimizationPipeline.run` let stage
     exceptions propagate, breaking the request (violates manifest design
     principle 3; `chat_completion` only guards `_call_api`). Fixed: per-stage
     try/except records `{stage}_error` metric and continues.
- **Verification (all green)**: `pytest tests/` 130 passed (77 existing
  untouched + 53 new); ruff clean; `mypy tokenopt` exit 0.
- **Coverage (ad hoc, per M3 acceptance)**: `cache.py` 68% → **96%**,
  `rag_optimizer.py` 24% → **98%**, suite total 72% → **89%** (formal 80%
  gate is M4).
- **STOPPING — awaiting approval to begin M4** (⚠ new HTTP stub dev dep).

## 2026-08-01 — Session 5: M2 — Pipeline Stage Tests 1 (router, compressor, summarizer)

### Work performed
- **Wrote 54 behavioral-contract tests** (network-free, public-contract only):
  - `tests/test_router.py` (18) — priority-ordered default rules
    (simple < code < reasoning) and custom rules; complexity fallback
    (high/medium/low keywords, 200/1000-token thresholds); empty messages,
    empty query, non-string user content → default model; rule-exception
    fail-open (skip rule, continue; all-failing → complexity fallback);
    last-user-message selection; first-match-stops-evaluation; determinism;
    no mutation of `ctx.messages`/`original_messages`.
  - `tests/test_compressor.py` (16) — heuristic path (whitespace collapse,
    filler-phrase removal, per-message truncation to target); message
    structure preserved (roles, extra keys); non-string content passthrough;
    empty/tiny/filler-only/missing-content edge cases; ML path via
    `_FakeCompressor` stub (prompt/rate/force_tokens contract, single-message
    replacement); ML failure → heuristic fallback (fail-open); lazy-load
    `_get_llmlingua` via `sys.modules` stub (None on missing, cached instance
    when present); determinism; no mutation.
  - `tests/test_summarizer.py` (13) — ≤2-message and below-threshold no-ops;
    ≤3 non-system no-op; reconstruction (system + summary + recent); no
    system message; custom `summarizer_fn` called with (history, model);
    extractive fallback (first/last user query, 200-char truncation,
    no-user-messages); malformed (list) content; determinism; no mutation.
  - `tests/test_pipeline_config.py` (5) — stage enable/disable gating through
    `OptimizationPipeline` (defaults on, all-off skip, independent switches,
    router rules applied, compressor compresses).
- **Defect exposed and fixed (minimal, no API change)**: `ContextSummarizerStage`
  kept the FIRST 3 non-system messages as "recent" and summarized the NEWEST
  ones — the opposite of its documented intent ("Keep last 3 messages"); the
  latest user query could be summarized away. Fixed with a two-pass split
  (recent = `non_system[-3:]`, history = `non_system[:-3]`; drop `reversed()`).
- **Verification (all green)**: `pytest tests/` 77 passed (23 existing
  untouched + 54 new); ruff clean; `mypy tokenopt` exit 0.
- **Coverage (ad hoc, per M2 acceptance)**: `router.py` 27% → **100%**,
  `compressor.py` (incl. summarizer) → **100%**, suite total 62% → **72%**
  (formal 80% gate is M4).
- **STOPPING — awaiting approval to begin M3** (cache/RAG/few-shot tests).

## 2026-08-01 — Session 4: M1 — Verification Gates (mypy gate fixed, DoD ratified)

### Work performed
- **Root-caused the mypy failure**: two independent causes —
  1. numpy 2.5 requires Python ≥ 3.12 (verified via wheel metadata
     `Requires-Python: >=3.12`) while tokenopt declares `>=3.10`; its `.pyi`
     stubs use PEP 695 `type` syntax that mypy cannot parse under
     `python_version = "3.10"` → syntax error at `numpy/__init__.pyi:737`.
  2. Optional extras (`redis`, `llmlingua`, `sentence_transformers`) not
     installed → `import-not-found`; code imports them fail-open (try/except).
- **Fix**: pinned `numpy>=1.24,<2.5` in `pyproject.toml` (runtime +
  typing compatibility with the declared 3.10 floor); added per-module mypy
  overrides `ignore_missing_imports` for the three optional extras so the
  gate does not require heavy optional installs. Local numpy downgraded
  2.5.1 → 2.4.6 to match the pin.
- **Fixed 37 real typing findings** mypy then surfaced (11 files): implicit
  Optional, missing `**kwargs: Any` / return annotations, `callable` vs
  `Callable`, `best_score` int→float, unused `# type: ignore`, `no-any-return`
  in embeddings (cast), `isinstance` narrowing for CacheStage, wrong
  `metrics_callback` annotation in `config.py` (runtime passes
  `RequestMetrics`, not `dict`).
- **Fixed latent runtime bug (typing gate exposed it)**: the original
  `ContextSummarizerStage.__init__(summarizer_fn)` was being called by
  `BaseOptimizedClient._build_pipeline` with the config positionally —
  any triggered summarization would have crashed calling the config object.
  Constructor now `(config, summarizer_fn=None)`, consistent with all stages.
- **Created `.ai/DOD.md`** — permanent Definition of Done: 5-gate pipeline
  (pytest, ruff, mypy, build, fresh-venv install+smoke), checklist,
  non-negotiables (no silent waivers), provenance.
- **Updated gates in docs**: AGENTS.md Git Rules (+`mypy tokenopt`),
  README Development section (+mypy, +build, +DoD link),
  `git-standard.md` (commit gate + pre-push checklist),
  `coding-standard.md` (type gate no longer "until fixed").
- **Verification (all green)**: `pytest tests/` 23 passed; `ruff` clean;
  `mypy tokenopt` exit 0; `python -m build` sdist+wheel; fresh venv wheel
  install + `import tokenopt` smoke OK.
- **STOPPING — awaiting approval to begin M2** (stage unit tests).

## 2026-08-01 — Session 3 (continued): Controlled shutdown per Decision 12

### Work performed
- Adopted AI Session Management Policy → **Decision 12** recorded
- Validation run: pytest 23 passed; ruff clean; `python -m build` OK;
  **mypy FAILS** (numpy 2.5 stubs vs py3.10 — recorded, not hidden; this is M1)
- Created `.ai/SESSION_STATE.md` (live status) and `.ai/TASK_QUEUE.md`
  (READY/IN PROGRESS/BLOCKED/DONE board for M1–M15)
- Updated `.ai/STANDARDS/ai-memory-standard.md` (SESSION_STATE, TASK_QUEUE,
  controlled-shutdown rule) and `AGENTS.md` (startup steps 9–10, session-close
  procedure, Decision 12 note)
- Updated CURRENT_STATE, ROADMAP (Phase 0 done), SESSION_LOG
- Final checkpoint `CHECKPOINT_20260801_0112.md`
- **STOPPED — waiting for explicit approval to begin M1**

## 2026-08-01 — Session 3 (continued): Phase 0 — AI Engineering Foundation

### Work performed
- **M0.1** — Created `.ai/STANDARDS/` (8 normative docs): coding,
  documentation, testing, git, release, security, ai-memory, checkpoint —
  each with rules, rationale, and verification commands
- **M0.2** — Created `.ai/WORKFLOWS/` (5 runbooks): implement-feature,
  fix-bug, code-review, release, handover
- **M0.3** — Created `.ai/ROLES/` (4 roles): architect, backend-engineer,
  reviewer, technical-writer
- Updated `PROJECT_MANIFEST.md` (§4 normative reference, §8 agent rules,
  §9 folder tree) and `AGENTS.md` (startup procedure + continuous
  improvement) to reference the new documents
- **No production code changed**
- Commits: standards / workflows / roles / manifest+manual references (4)
- Memory updated (CURRENT_STATE, NEXT_STEPS); checkpoint created
- Pushed to `rohit-naik36/TokenOpt` (remote verified per Decision 11)
- **STOPPING — awaiting approval to begin M1** (mypy gate fix)

## 2026-08-01 — Session 3 (continued): Repository audit + implementation roadmap

### Work performed
- Ran evidence-gathering for audit: line counts, git history (17 commits),
  `pytest --cov` (62% total; rag_optimizer 24%, router 27%, anthropic 37%),
  `mypy` (broken — numpy 2.5 stubs vs py3.10 target), secrets scan (clean)
- Created `.ai/REPOSITORY_AUDIT.md` — 12 categories, overall 6.4/10,
  weaknesses ranked, prioritized improvement plan, proposed `.ai/`
  STANDARDS/PROMPTS/WORKFLOWS/ROLES scaffolding; **no changes implemented**
- Created `.ai/IMPLEMENTATION_ROADMAP.md` — 15 milestones (≤1 day each,
  independently testable, full ceremony each: tests/lint/docs/memory/commit/
  push/checkpoint), Phase A–E, approval-gate tags, sequencing rationale
- Committed and pushed both documents (remote verified per Decision 11)
- **No implementation performed** — awaiting user approval

## 2026-08-01 — Session 3 (continued): Repository-wide AGENTS.md

### Work performed
- Created root `AGENTS.md` — tool-agnostic operating manual (OpenCode,
  Claude Code, Cursor, GitHub Copilot, ChatGPT, Gemini, future agents):
  project overview, agent responsibilities, startup procedure (9-step read
  order), development rules, documentation rules, git rules, checkpoint rules,
  approval gates, session close procedure, continuous improvement
- Aligned with `.ai/PROJECT_MANIFEST.md` (manifest wins on conflict) and
  Decision 11 (remote verification before push)
- Committed: `docs: add repository-wide agent operating manual`
- Updated CURRENT_STATE.md (AGENTS.md created)

## 2026-08-01 — Session 3 (continued): Project manifest ratified

### Work performed
- Created `.ai/PROJECT_MANIFEST.md` (Revision 1.0) — project constitution with
  11 sections: overview, product definition, technical vision, engineering
  standards, git strategy, development workflow, definition of done, AI agent
  rules, repository conventions, release process, long-term vision (v1/v2/v3)
- Verified markdown formatting; committed `docs: add project manifest (constitution)`
- Updated CURRENT_STATE.md (manifest ratified, AGENTS.md noted as missing)

## 2026-08-01 — Session 3 (continued): Remote handling rule

### Work performed
- User rule: never modify the Git remote automatically; before any push verify
  `git remote -v` and URL pattern `github.com/<username>/<repository>.git`;
  if missing/malformed, stop and ask for approval; never guess or rewrite
- Verified current remote: `https://github.com/rohit-naik36/TokenOpt.git` (valid)
- Recorded as Decision 11 in `.ai/DECISIONS.md`

## 2026-08-01 — Session 3 (continued): Session close / handover

### Work performed
- Verified clean working tree and 10 committed logical commits
- Diagnosed invalid `origin` remote (mangled URL from a pasted command —
  `git-remote-add-origin-https---github.com--your-username--tokenopt...`)
- User provided correct repo URL → fixed `origin` to
  `https://github.com/rohit-naik36/TokenOpt.git` and pushed `main`
  (11 commits, up to date)
- Final checkpoint `CHECKPOINT_20260801_0046.md` created
- Re-verified: tests 23 passed, ruff clean, editable install OK

## 2026-08-01 — Session 3: Version control, project memory, baseline commits

### Work performed
- Established git repo (`main`), `.gitignore`, commit workflow rules
- Created `.ai/` project memory (CURRENT_STATE, NEXT_STEPS, DECISIONS, ROADMAP,
  ARCHITECTURE, SESSION_LOG) + milestone checkpoint `CHECKPOINT_20260801_0036`
- Created `README.md` (referenced by `pyproject.toml` — packaging would fail without it)
- Fixed packaging: explicit `[tool.setuptools] packages` (stray artifact dirs
  broke `pip install -e .`); ruff config sections corrected
- Fixed lint debt across pre-existing modules (64+ findings: F401, E501, I001,
  W292, F841) incl. latent bug — `count_message_tokens` used but never imported
  in `tokenopt/pipeline/compressor.py`
- Committed all existing work in 9 logical commits
- Verified: 23 tests pass, ruff clean, editable install works

### Context (prior sessions)
- Session 2 (previous chat): implemented `local_client.py`, `factory.py`,
  package `__init__` files, 23 tests; fixed invalid TOML in pyproject,
  added numpy dependency; installed missing deps; updated SESSION_BACKUP.md
- Session 1 (original build): Phase 1 core modules (config, utils, pipeline
  stages, observability, OpenAI/Anthropic clients)

## 2026-08-01 — Session 18: M13 — Structural Refactoring & Architecture Stabilization

### Work performed
- Full read of every `tokenopt/` module (~1,300 LOC, 12 modules); line
  inventory; hotspots identified (H1–H11) and reported in
  `.ai/M13_ARCHITECTURE_REVIEW.md` §1.
- **R1** — shared `get_user_query` in new `utils/messages.py`; removed three
  identical copies (router, rag, fewshot); `_reconstruct_messages` takes the
  precomputed query.
- **R2** — typed `config: TokenOptConfig | None = None` + `TokenOptConfig()`
  default in all five stage constructors (compressor, summarizer, cache,
  rag, fewshot) matching RouterStage; dropped dead `self.config and` guard
  in `CacheStage._get_redis`.
- **R3** — `clients/base.py::_extract_openai_shape_usage` shared by OpenAI +
  LocalClient (`_extract_usage` methods kept, delegate to it).
- **R4** — `clients/_compat.py::_CompatShim`; chat/messages shims in all
  three clients now instantiate it (three identical forwarders removed).
- **R5** — `BaseOptimizedClient._build_pipeline(routing_rule_filter=None)`
  owns "default pipeline minus router, plus scoped router";
  Anthropic/LocalClient pass model-compatibility filters (AND-ed with any
  caller filter); duplicated `dataclasses.replace` dance removed.
- **R6** — `FewShotSelectorStage` split to `pipeline/fewshot.py`
  (rag_optimizer.py 278 → 145 lines); `tokenopt.pipeline` exports
  unchanged; test imports updated (test_fewshot, test_pipeline_config).
- Deliberately NOT refactored (documented with rationale): diversity
  re-embedding (H7), `compression_attempted` alias (H8), stage gating (H9),
  MODEL_COSTS table (H10), unkeyed metrics dicts (H11) — all tracked in ADB.
- `.ai/M13_ARCHITECTURE_REVIEW.md` — hotspot report (§1), refactoring
  summary (§2), internal architecture assessment (§3), technical debt
  report (§4, 4-way classification), self-review with Immediate
  Recommendations + ADB-01..10 (§5), validation summary (§6).
- Verification: pytest 167 passed (coverage 94% — baseline unchanged),
  ruff clean, mypy green (23 files), `python -m build` sdist+wheel OK,
  `twine check dist/*` PASSED (twine installed), 6/6 examples exit 0 vs
  stub server (127.0.0.1:8787, restarted then stopped PID 20168), link
  check over 83 `.ai/` md files clean.
- Decision 25 — future operating model: every milestone completion report
  uses the six-section format (Milestone Summary / Verification Results /
  Architectural Improvements / Immediate Recommendations / ADB /
  Recommendation for Approval).
- Roadmap deviation notes (documented in IMPLEMENTATION_ROADMAP M13):
  MODEL_COSTS not relocated (ADB-05, churn without value under the brief's
  high-value-only mandate); router complexity keywords left as a class
  attribute (already a single named constant).
- Commits: see git log — 5 logical commits (refactor ×3, docs, chore memory).
- Suite **167 passed, coverage 94%**; pushed; CI green (polled badge).

## 2026-08-01 — Session 19: M14 — Architecture Knowledge Base

### Work performed
- Phase 1 review: read ARCHITECTURE.md, GOVERNANCE_INDEX.md, README
  structure/Project-structure section — no inconsistencies found to fix in
  runtime code (docs-only milestone; behavioral freeze).
- **Phase 2 — Knowledge Base** `.ai/KNOWLEDGE_BASE/` (10 files):
  README (index + reading order); 01 System Overview (goals, drop-in
  philosophy, fail-open, optimization philosophy, routing philosophy,
  package structure); 02 Request Lifecycle (7 transitions explained,
  lifecycle branches, Mermaid sequence diagram — cache hit/miss/error);
  03 Pipeline (execution order + why, stage responsibilities table, stage
  interactions, fail-open, gating map, context lifecycle); 04 Provider
  Layer (4-seam abstraction, provider responsibilities, OpenAI/Anthropic/
  LocalClient, **response-normalization contract spec**, factory);
  05 Configuration (hierarchy, groups table, defaults incl. builtin rules,
  overrides, validation, extension strategy); 06 Metrics (ownership
  layers, propagation flow, routing_reason 3-way, routing_precedence 5
  values, latency trio, cost, observability philosophy).
- **Phase 3 — Contracts** 07_ARCHITECTURAL_CONTRACTS.md: C1 public API
  stability, C2 routing precedence, C3 fail-open, C4 pipeline order,
  C5 metrics ownership, C6 provider abstraction, C7 configuration
  ownership, C8 local normalization — each with contract/why/enforcement,
  plus "how contracts change".
- **Phase 4 — Extension Guide** 08_EXTENSION_GUIDE.md: principles +
  recipes for provider/stage/metrics/config/optimization stages + what
  requires approval (no implementation).
- **Phase 5 — Internal Assessment** 09_INTERNAL_ASSESSMENT.md: Software
  Factory view — strengths, limitations, reusable components/patterns,
  extension points, **ADB-11** (internal architecture contracts,
  required), **ADB-12** (machine-readable manifest), **ADB-13**
  (normalization enforcement).
- Wiring: ARCHITECTURE.md pointer section; GOVERNANCE_INDEX Knowledge
  Base registry (owners, normative rule); README pointer line.
- **Phase 6 — Validation**: Decision 24 precedence paths (router.py
  grep), routing_reason fallback (base.py), metrics vocabulary, config
  groups cross-checked vs code — all match; 29/29 markdown links +
  31/31 KB inline paths resolve (2 `test_metrics_clarity.py` path typos
  found + fixed); examples untouched (git status); suite 167 unchanged.
- Memory: IMPLEMENTATION_ROADMAP M14 ✅, ROADMAP checkbox, TASK_QUEUE,
  NEXT_STEPS, SESSION_STATE, CURRENT_STATE; checkpoint
  CHECKPOINT_20260801_M14.md.
- Commits: `docs:` ×2 (knowledge base + memory/checkpoint); pushed;
  CI green (polled badge).

## Session 20 — M15: Release v0.1.0 to PyPI (2026-08-02)

- **Context**: User confirmed Trusted Publisher configured on PyPI (project
  `tokenopt` / owner `rohit-naik36` / workflow `publish.yml`) — status
  showed "pending" because no OIDC publish had happened yet.
- **Diagnosis**: `publish.yml` triggers only on `v*` tags and no tag
  existed; PyPI (and TestPyPI) JSON APIs returned 404 for `tokenopt`;
  `pip index versions tokenopt` found nothing. Trusted Publisher "pending"
  = registered but never used; flips to `active` after first successful
  upload.
- **Executed**: verified `git remote -v` (Decision 11) — created + pushed
  annotated tag `v0.1.0` — GitHub Actions publish workflow ran (build
  sdist+wheel, `twine check`, OIDC upload via `pypa/gh-action-pypi-publish`
  with `id-token: write`; no secrets).
- **Verified**: `https://pypi.org/pypi/tokenopt/json` — 200, version 0.1.0
  (was 404 pre-publish). `pip install tokenopt` now works.
- **Memory updated**: CURRENT_STATE (M15 entry, in-progress trimmed),
  NEXT_STEPS (M15 done → ADB backlog), SESSION_STATE, TASK_QUEUE (M15
  DONE, resolved gates), ROADMAP (M15 checkbox), SESSION_LOG.
- **Checkpoint**: CHECKPOINT_20260802_M15.md (created below).
- Note: untracked `TEST.txt` ("hello") left in repo root — pending user
  decision (not committed).

## Session 20.1 — Team testing guide (2026-08-02)

- **Created `docs/TEAM_TESTING_GUIDE.md`** (user request: shareable
  document for the team to test TokenOpt v0.1.0):
  - Scope/what-is-being-tested, prerequisites, setup (PyPI install +
    editable, extras, API keys)
  - Test matrix at a glance (12 scenarios, offline/live marked)
  - **Part A** — offline automated suite (import/version, `pytest tests/`
    167 passed/94%, fresh-venv PyPI install)
  - **Part B** — all 6 examples (quickstart, openai_basic, anthropic_basic,
    local_basic, pipeline_config, metrics_observability) with explicit
    PASS criteria per script, cross-checked against the actual example
    code (metrics fields, routing reasons, cache miss→hit, summarization
    threshold)
  - **Part C** — contract checks (drop-in swap, fail-open/error handling,
    no-secrets-leak)
  - **Part D** — deep features (routing precedence Decision 24, config
    gates)
  - **Part E** — known v0.1.0 limitations (streaming, per-instance cache,
    semantic fallback, Python 3.10–3.12)
  - **Appendix A** — stdlib-only offline stub server (no API keys needed)
  - **Appendix B** — GitHub issue bug-report template + sign-off table
- Docs-only; no code/tests changed; suite remains 167 green.
- **Session 20.2 (same day)** — per user request, merged the UAT checklist
  into the guide as **Appendix C** (verbatim from `docs/UAT.md`, marked as
  canonical-copy; `docs/UAT.md` stays the source of truth) — the guide is
  now a single self-contained document; intro + footer updated.
