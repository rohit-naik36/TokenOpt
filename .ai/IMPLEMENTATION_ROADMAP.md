# TokenOpt SDK — Prioritized Implementation Roadmap

_Status: APPROVED (2026-08-01, with Phase 0 modification). M1 DONE — see below._
_Origin: `.ai/REPOSITORY_AUDIT.md` (2026-08-01, overall 6.4/10)_
_Principle: engineering quality first — verification gates and test coverage
precede any new product features. Feature work resumes only after M1–M7._

---

## 0. How to read this roadmap

- Each milestone (M1–M15) is sized for **≤ 1 agent-day** and is
  **independently testable**: it ships only when its own acceptance checks pass.
- Every milestone ends with the full ceremony:
  1. tests pass, 2. lint passes, 3. docs updated, 4. `.ai/` memory updated,
  5. commit, 6. push (remote verified per Decision 11), 7. checkpoint.
- Milestones with a **⚠ approval** tag touch an Approval Gate
  (dependency change, file deletion, license, publish) and must not start
  until the user approves.
- Milestones are sequential unless noted "parallelizable".
- A milestone is "Done" only when its **Acceptance check** is demonstrably green.

---

## Phase A — Verification gates (M1–M5)

### M1 — Fix the type-checking gate — ✅ DONE (2026-08-01)

**Problem:** `mypy tokenopt` fails before analyzing any project code (numpy 2.5
`.pyi` files use Python ≥ 3.12 `type` statements; config targets 3.10).

**Resolution (as implemented):**
- Pinned `numpy>=1.24,<2.5` in `pyproject.toml` — numpy 2.5 requires
  Python ≥ 3.12 at runtime (incompatible with the declared `>=3.10` floor)
  and its stubs are unparseable by mypy under `python_version = "3.10"`.
  The pin fixes both runtime matrix and type gate.
- Added per-module mypy overrides (`ignore_missing_imports`) for the optional
  extras `redis.*`, `llmlingua.*`, `sentence_transformers.*` — the gate must
  not require installing heavy optional dependencies.
- Fixed 37 real typing findings mypy then surfaced (implicit Optional,
  missing annotations, `callable` vs `Callable`, `no-any-return` casts,
  wrong `metrics_callback` annotation, CacheStage narrowing), including one
  latent runtime bug (ContextSummarizerStage receiving config where a
  callable was expected).
- `mypy` added to the commit gate: AGENTS.md Git Rules, README dev section,
  `.ai/DOD.md`, git/coding standards.

**Acceptance check** — `mypy tokenopt` exits 0 ✅; `pytest tests/` 23/23 ✅;
`ruff` clean ✅; build + fresh-venv smoke ✅.

---

### M2 — Pipeline stage tests, part 1: router + compressor + summarizer — ✅ DONE (2026-08-01)

**Work** (all network-free, pure unit tests) — **as implemented:**
- `tests/test_router.py` — 18 behavioral-contract tests: default rules by
  priority (simple < code < reasoning) and custom rule priority ordering;
  complexity fallback (high/medium/low keyword scoring, 200/1000-token
  thresholds); empty-query/empty-messages/non-string-content paths (default
  model); rule exceptions skipped without crashing (fail-open, incl.
  all-rules-failing → complexity fallback); last-user-message selection;
  first-match-stops-evaluation; determinism; no mutation of
  `ctx.messages`/`original_messages`.
- `tests/test_compressor.py` — 16 tests: heuristic path (whitespace collapse,
  filler removal, per-message truncation to target); LLMLingua absence
  fallback (`sys.modules` stub → None, cached when present); ML path with a
  `_FakeCompressor` stub incl. fail-open fallback when ML raises; tiny/empty/
  filler-only/missing-content prompts; message format preserved (roles, extra
  keys, non-string content passthrough); determinism; no mutation.
- `tests/test_summarizer.py` — 13 tests: threshold gating (below = no-op);
  ≤2-message and ≤3-non-system no-ops; custom `summarizer_fn` used when
  provided (called with history + model); extractive fallback (first/last
  user query, 200-char truncation, no-user-messages); system-message
  reconstruction (with and without system message); malformed content;
  determinism; no mutation.
- `tests/test_pipeline_config.py` — 5 tests: per-stage enable/disable gating
  through `OptimizationPipeline` (defaults on, all-off skip, independent
  switches).
- **Defect found + fixed (minimal, no API change):** `ContextSummarizerStage`
  kept the *first* 3 non-system messages as "recent" and summarized the
  *newest* ones — opposite of the documented "Keep last 3 messages" intent
  (latest user query could be summarized away). Fixed: recent =
  `non_system[-3:]`, history = `non_system[:-3]`, drop `reversed()`.

**Acceptance check**
- New suites green ✅ — `pytest tests/` 77 passed (23 pre-existing unaffected);
- Coverage for `router`/`compressor` above 70% ✅ — router 27% → **100%**,
  compressor (incl. summarizer) → **100%**, suite 62% → **72%** (ad hoc;
  formal gate is M4) — measured with `pytest --cov`.

---

### M3 — Pipeline stage tests, part 2: cache + RAG + few-shot — ✅ DONE (2026-08-01)

**Work** (all network-free, pure unit tests, scripted embedding providers) —
**as implemented:**
- `tests/test_cache.py` (18) — exact-key hit/miss + store roundtrip; semantic
  hit at threshold / miss below; TTL expiry (exact + semantic); LRU eviction
  at `cache_max_size`; model-mismatch no-hit; `clear()`/`stats()`; Redis path
  with mocked client (roundtrip + failure fail-open); store without metadata
  no-op; non-string content; determinism; no mutation.
- `tests/test_rag_optimizer.py` (15) — chunk parsing (`context:`/`retrieved:`
  + `rag_chunks` key); similarity ranking, retention threshold, `rag_max_chunks`
  cap; dedup (near-duplicates removed, distinct kept, correct embeddings after
  reorder); no-context/no-query no-ops; malformed content; determinism; no
  mutation.
- `tests/test_fewshot.py` (13) — similarity/diversity/random selection
  strategies; max-examples caps + fewer-than-max; default config; injection
  order/format; metrics; determinism; no mutation.
- `tests/test_pipeline_config.py` (+7) — cache gating; RAG/few-shot always-on;
  pipeline fail-open.
- **4 defects found + fixed (minimal, no API change):** (1) cache key
  collision for non-string content (json-dump normalization); (2) RAG dedup
  compared misaligned embeddings after re-sort (embeddings now carried
  through sort); (3) few-shot nothing injected when no system message
  (examples prepended); (4) pipeline stage exceptions broke requests —
  `OptimizationPipeline.run` now fails open per stage with `{stage}_error`
  metric (manifest design principle 3).

**Acceptance check**
- New suites green ✅ — `pytest tests/` 130 passed (77 pre-existing unaffected);
- Coverage for `rag_optimizer`/`cache` ≥ 70% ✅ — cache 68% → **96%**,
  rag_optimizer 24% → **98%**, suite 72% → **89%** (ad hoc; formal gate M4).

---

### M4 — Integration tests + formal coverage gate

**Work**
- `tests/integration/` with mocked HTTP servers (OpenAI-compatible, Anthropic,
  Ollama) using an HTTP-stubbing library (e.g. `responses` or `pytest-httpx`):
  - Full drop-in flow: optimize → call → cache store → metrics recorded
  - Cache hit on second identical request (no second network call)
  - Error path: provider failure records metrics and re-raises (fail-open of stages)
  - Factory + LocalClient against OpenAI-compatible and Ollama-shaped servers
- Configure `[tool.coverage]` in `pyproject.toml`: fail-under **80%** for
  `tokenopt/`; add `--cov` to pytest `addopts`.

**Acceptance check**
- `pytest tests/` green **and** coverage gate ≥ 80% enforced by pytest itself.

**⚠ Approval needed:** new dev/test dependency (HTTP stub library).

---

### M5 — CI pipeline (GitHub Actions)

**Work**
- `.github/workflows/ci.yml`: matrix Python 3.10/3.11/3.12 → `ruff` → `mypy` →
  `pytest --cov` (gate from M4) → `python -m build` + wheel smoke install
  (`import tokenopt` in a fresh venv).
- Enable branch protection notes in CONTRIBUTING (docs only; org settings are
  user-administered).

**Acceptance check**
- Push to a branch → CI green on GitHub for all matrix cells; local equivalents
  also green. (This is the first milestone verified *on* GitHub.)

---

## Phase B — Release & security engineering (M6–M7)

### M6 — Release metadata: license, classifiers, changelog, build

**Work**
- Add `LICENSE` file (proposed: MIT — user decides) + `license`, `authors`,
  `classifiers`, `project.urls` in `pyproject.toml`.
- Create `CHANGELOG.md` (unreleased v0.1.0 section; format per manifest §10).
- Verify `python -m build` produces sdist + wheel; smoke-install the wheel.

**Acceptance check**
- `pip install .` from built wheel works; metadata renders on PyPI-check
  (`python -m build` + `twine check` if available).

**⚠ Approval needed:** license selection; metadata content.

---

### M7 — Security hardening: dependency + secret scanning

**Work**
- Add `pip-audit` (and optional lockfile) to dev tooling; document audit run.
- Add secret scanning (e.g. gitleaks or trufflehog) locally + CI step.
- Add CI steps for both; enable Dependabot config `.github/dependabot.yml`.

**Acceptance check**
- `pip-audit` clean on current deps; secret scan clean on repo; both run in CI.

**⚠ Approval needed:** new dev dependencies; Dependabot enablement.

---

## Phase C — Developer experience (M8) + governance docs (M9–M11)

### M8 — Onboarding: CONTRIBUTING, Makefile, examples

**Work**
- `CONTRIBUTING.md` — setup, test/lint/type commands, PR expectations, DoD.
- `Makefile` (or `noxfile.py`) — `test`, `lint`, `type`, `coverage`, `build`.
- `examples/` — 3 runnable scripts: (1) OpenAI drop-in + metrics,
  (2) factory auto-detect + LocalClient, (3) custom config + custom routing rule.

**Acceptance check**
- Fresh-clone instructions work: `make test` green; each example runs.

---

### M9 — Ratify `.ai/STANDARDS/` (8 documents)

**Work** — codify current prose rules as standalone standards:
`coding-standard.md`, `documentation-standard.md`, `testing-standard.md`,
`git-standard.md`, `release-standard.md`, `security-standard.md`,
`ai-memory-standard.md`, `checkpoint-standard.md`. Each states the rule, the
rationale, and the verification command/check. AGENTS.md and manifest stay the
entry points; standards become the normative detail.

**Acceptance check**
- Each standard is internally consistent with manifest + AGENTS.md (review);
  no code changes; memory updated.

---

### M10 — Ratify `.ai/WORKFLOWS/` (subset) + `.ai/ROLES/`

**Work** (per audit §5 opinion — start with the subset that has real users here)
- `WORKFLOWS/`: `Idea_to_PRD.md`, `PRD_to_Architecture.md`,
  `Story_to_Implementation.md`, `Test_to_Release.md`
- `ROLES/`: `ProductManager.md`, `SolutionArchitect.md`, `BackendEngineer.md`,
  `QAEngineer.md`, `TechnicalWriter.md`, `Reviewer.md`

**Acceptance check**
- Workflows cross-reference the ceremonies in AGENTS.md; roles map to
  responsibilities therein; review-consistent.

---

### M11 (optional) — `.ai/PROMPTS/` (9 documents)

**Work** — reusable agent prompts: architecture, implementation, refactoring,
documentation, testing, code-review, release, handover, debugging.

**Acceptance check** — each prompt used at least once against a real task
during the milestone (self-test) or explicitly deferred.

---

## Phase D — Structure & maintainability (M12–M13)

### M12 — Structure cleanup + GitHub templates

**Work**
- Delete the seven empty artifact dirs (`CProjectsNew/`, `Idea_Factory/`,
  `Projecttests/`, `Projecttokenopt*`) — **⚠ file deletion approval**.
- Archive `SESSION_BACKUP.md` (move to `.ai/archive/` or mark archived) to stop
  memory drift — **⚠ deletion/relocation approval**.
- Add `.github/PULL_REQUEST_TEMPLATE.md` + issue templates; `CODEOWNERS` if a
  team exists (else document single-maintainer posture).

**Acceptance check**
- Root tree contains only intentional entries; templates present; git history
  intact (nothing deleted from history).

---

### M13 — Maintainability refactor (no behavior change)

**Work**
- Extract shared response/usage helpers (dedupe `_extract_usage`/
  `_extract_response_content` across the three client wrappers).
- Move `MODEL_COSTS` to a data module with a documented update policy.
- Extract router complexity-keyword constants.

**Acceptance check**
- Full suite green after refactor with **identical** test assertions
  (behavior-preserving); coverage unchanged or better.

---

## Phase E — Documentation polish + first release (M14–M15)

### M14 — Architecture documentation polish

**Work**
- Add Mermaid sequence diagrams (request lifecycle: cache hit / miss / error).
- Write the response-normalization contract spec (LocalClient → OpenAI shape).
- Add "how to add a provider / custom stage" extension guide to README.

**Acceptance check**
- Diagrams render; contract spec reviewed against `local_client.py` behavior;
  README guide is step-by-step executable.

---

### M15 — Release v0.1.0

**Work** (per manifest §10)
- Finalize CHANGELOG; bump/verify version (`0.1.0`); clean-checkout verification
  (tests, lint, mypy, build).
- Tag `v0.1.0`; push tag (remote verified); publish GitHub release notes.
- **Optional:** publish to PyPI (user decision — **⚠ deployment/publish
  approval**).

**Acceptance check**
- `git ls-remote --tags` shows `v0.1.0`; release notes live; post-release
  checkpoint + CURRENT_STATE updated.

---

## 1. Sequencing rationale

1. **M1 before M2/M3** — a working type gate is the cheapest catch-all; fixing
   numpy first prevents the numpy/mypy issue from re-breaking CI later.
2. **M2/M3 before M4** — unit tests build the foundation the integration tests
   and coverage gate measure.
3. **M4 before M5** — CI enforces an already-green local gate; avoids
   fighting CI and code issues at once.
4. **M5 before M6/M7** — release metadata and scans are only valuable once
   they are *enforced* by CI.
5. **M8/M9–M11** — developer experience and governance docs are independent
   of code risk; safe to do after gates exist (parallelizable with M6/M7 if
   desired).
6. **M12/M13** — deletions and refactors happen after tests+coverage+CI are in
   place, so every structural change is guarded.
7. **M15 last** — the release ships only on a fully verified base.

## 2. Estimated totals

- 15 milestones, ~15 agent-days of sequential work (parallelizable pairs
  can compress to ~11).
- Feature work (Phase 2 product items in `.ai/ROADMAP.md`: streaming, cache
  persistence, LLMLingua, Prometheus, dynamic routing) starts **after M7** and
  is deliberately not scheduled here — engineering quality precedes features.

---

_End of roadmap. Awaiting approval. No milestones have been started._
