# Task Queue

_Updated: 2026-08-01 (M14 DONE — Architecture Knowledge Base complete)_

Statuses: `READY` · `IN PROGRESS` · `BLOCKED` · `DONE`
Tasks map to milestones in `.ai/IMPLEMENTATION_ROADMAP.md`.

## DONE

| Task | Notes |
|------|-------|
| Baseline v0.1.0 (Phase 1) | 23 tests, lint clean, build OK |
| Git repo + 17→24 commits + push | `rohit-naik36/TokenOpt` |
| `.ai/` memory foundation (7 docs + manifest + AGENTS.md) | — |
| Repository audit | `REPOSITORY_AUDIT.md`, overall 6.4/10 |
| Implementation roadmap | approved with Phase 0 modification |
| **M0.1** — `.ai/STANDARDS/` (8 files) | — |
| **M0.2** — `.ai/WORKFLOWS/` (5 files) | — |
| **M0.3** — `.ai/ROLES/` (4 files) | — |
| Manifest + AGENTS.md references | §4/§8/§9 + startup procedure |
| Session management policy adopted | Decision 12, this queue + SESSION_STATE.md |
| **M1** — Verification Gates | `mypy tokenopt` exit 0; numpy pin `>=1.24,<2.5`; 37 typing fixes + latent summarizer bug; `.ai/DOD.md` ratified; docs gates updated |
| **M2** — Pipeline Stage Tests 1 | 54 new behavioral-contract tests (router 18, compressor 16, summarizer 13, gating 5); router/compressor coverage 27%/… → **100%**; **defect fixed**: summarizer kept oldest messages as recent (now keeps last 3); suite 77 passed |
| **M3** — Pipeline Stage Tests 2 | 53 new tests (cache 18, RAG 15, few-shot 13, gating+7); cache 68%→**96%**, rag_optimizer 24%→**98%**, suite **89%**; **4 defects fixed**: cache key collision (non-string content), RAG dedup embedding misalignment, few-shot injection w/o system message, pipeline fail-open; suite 130 passed |
| **M4** — Integration Tests + Coverage Gate | `INTEGRATION_TEST_STRATEGY.md`; `tests/integration/` 19 tests via `httpx.MockTransport` (**zero new deps** — `http_client=` kwarg); **2 defects fixed**: `chat.completions.create` drop-in surface (Decision 14), Anthropic router scoped to claude models (Decision 13); `[tool.coverage] fail_under=80` + `--cov` addopts; suite **149 passed, coverage 94%** |
| **M5** — CI Pipeline | `.github/workflows/ci.yml` — lint / test matrix (3.10–3.12) / package+build+smoke; `CONTRIBUTING.md` (CI docs + branch protection notes); README badge; **verified green on GitHub** (run 30664914071); **2 CI-found defects fixed** (ollama mypy override; clear error for missing ollama — Decision 16); suite **150 passed, coverage 94%** |
| **M6** — Release Metadata | MIT LICENSE (user decision); CHANGELOG.md (Keep a Changelog, `[0.1.0]`); pyproject metadata complete (author, keywords, 9 classifiers, URLs, PEP 639 `license = "MIT"`, `setuptools>=77` — Decision 17); README release review (providers/extras/status/license); **build ✅ + `twine check` PASSED + fresh-venv metadata ✅**; suite **150 passed, coverage 94%** |
| **M7** — Security Baseline | author → "Rohit Naik"; pip-audit 0 vulns + CI security job; gitleaks 8.30.1 full-history (58 commits, no leaks); dependabot.yml weekly; SECURITY.md; CONTRIBUTING security section; CI run 30666354747 all green; suite **150 passed, coverage 94%** |
| **M8** — Onboarding | examples/ (6 scripts); README rewrite (Quick Start, extras, FAQ); Makefile; CONTRIBUTING; clean-env validation vs stub server (6/6 exit 0); defect fixed (F821 in metrics_observability.py); suite **150 passed, coverage 94%** |
| Post-M8 UAT refinements | metrics clarity (attempted/effective/tokens_saved/reduction_pct/model_latency_ms — additive); _format.py readable blocks; 5-Minute Quick Start; docs/UAT.md; +5 regression tests (155 total); suite **155 passed, coverage 94%** |
| **M8.2** — Value Demonstration & Showcase | `RequestMetrics.routing_reason` (additive, from ctx.metrics — rule name or `complexity-based (low|medium|high)`); `_format.py` `explain()` + `print_comparison()`; 6 examples rewritten as value demos (header docstrings, long prompts, OFF vs ON + miss→hit, truthful explanations); README/CHANGELOG; +3 regression tests (158 total); clean-env validation 6/6 exit 0, cross-checked truthful; commits `203b3d4`/`ec4f638`/`2a6093f`; suite **158 passed, coverage 94%**, CI green |
| **M10** — AI Engineering Governance Expansion (Decision 21) | Review findings I1–I8 fixed; WORKFLOWS 5 → **14** (9 new: refactoring, architecture-review, documentation-update, dependency-upgrade, security-response, performance-investigation, uat-execution, regression-verification, repository-audit; unified template + standardized gates); ROLES 4 → **11** (7 new: product-strategist, product-manager, qa-engineer, security-reviewer, release-manager, devops-engineer, repository-auditor; authority/inputs/success criteria); `.ai/GOVERNANCE_INDEX.md` registry + `.ai/GOVERNANCE_REVIEW.md`; AGENTS.md + roadmaps updated (M9 marked covered-by-M0.1); link check 64/64 resolve; SDK untouched; commits `72ddef0`→`104d366`; suite **158 passed** |
| **M11** — AI Prompt Library (Decision 22) | `.ai/PROMPTS/` grouped by purpose: design (architecture-review), implementation (feature, bug-fix, refactoring, unit-testing), verification (integration-testing, regression-verification), operations (documentation-update, release-preparation, repository-audit) — **10 prompts**; fixed template (objective, inputs, deterministic steps with exact commands/paths, outputs, verification criteria, determinism rules); `.ai/PROMPTS/README.md` design guidelines (layer model, add/maintain rules); GOVERNANCE_INDEX Prompts table; cross-refs 10/10 resolve; link check 75/75; SDK untouched; suite **158 passed** |
| **M12** — Repository Curation (Decision 23) | Deleted: 7 empty artifact dirs (`C?ProjectsNew/`, `Idea_Factory/`, `Projecttests/`, `Projecttokenopt*`) + generated artifacts (`dist/`, `tokenopt.egg-info/`, `.coverage`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, 8× `__pycache__/`). Archived: `SESSION_BACKUP.md` → `.ai/ARCHIVE/` (git mv, history intact; audit finding 9 closed). Created: `.ai/REPOSITORY_RETENTION_POLICY.md` (permanent/archived/regenerated/disposable/user-owned) + `.ai/REPOSITORY_INVENTORY.md` (classification + ledger). Added: GitHub PR/issue templates + CODEOWNERS (single-maintainer). Updated: REPOSITORY_AUDIT §7 dated closure (findings 6+9, plan item 8), GOVERNANCE_INDEX Policies section, repository-audit workflow (curation step). Link check 79/79; suite **158 passed**; SDK untouched |
| **Pre-M13** — Routing Precedence (Decision 24) | Five-level contract (least surprise): explicit caller model wins → matching rule → custom no-match **preserves caller's model** → no custom rules = complexity routing → provider default. `RoutingRule.builtin` provenance (default rules marked; default-config behavior unchanged); `model_explicit` plumbing (OptimizationContext + pipeline.run + chat_completion, additive); RouterStage records `routing_precedence` (explicit/rule/preserve/complexity/provider_default); `routing_reason` += "preserved (no rule matched)"; `RequestMetrics.routing_precedence` (additive). **Fixes**: no `gpt-*` rewrite on no-match (Anthropic/local invalid-model break). Review: `.ai/ROUTING_PRECEDENCE_REVIEW.md`. Tests +9 (167 total); examples revalidated 6/6 exit 0 against stub; docs: ARCHITECTURE/README/CHANGELOG |
| **M13** — Structural Refactoring & Architecture Stabilization (Decision 25) | Internal-only, behavioral freeze (no public API / routing / metrics / governance changes). **R1** `utils/messages.py::get_user_query` (3 copies removed; `_reconstruct_messages` precomputes query); **R2** `config: TokenOptConfig|None` + default in all 5 stage constructors; **R3** `_extract_openai_shape_usage` shared by OpenAI/LocalClient; **R4** `clients/_compat.py::_CompatShim` (3 identical shim forwarders removed); **R5** `_build_pipeline(routing_rule_filter)` — Anthropic/LocalClient pass model-compatibility filters (duplicated rebuild pattern + `replace` dance removed); **R6** `FewShotSelectorStage` → `pipeline/fewshot.py` (exports unchanged; test imports updated). **Deferred with rationale** (ADB): diversity re-embedding (H7), `compression_attempted` alias (H8), stage gating (H9), MODEL_COSTS (H10), unkeyed metrics dicts (H11). **Deliverable**: `.ai/M13_ARCHITECTURE_REVIEW.md` (hotspots, refactoring summary, architecture assessment, 4-way debt report, Immediate Recs + ADB-01..10, validation). **Verification**: 167 passed / 94% (baseline unchanged), ruff clean, mypy green, build + twine check PASSED, 6/6 examples vs stub, link check 83 files; CI green |
| **M14** — Architecture Knowledge Base | Docs-only (behavioral freeze: no runtime code changed). **Deliverable**: `.ai/KNOWLEDGE_BASE/` (10 files) — index; 01 System Overview (goals, fail-open/optimization/routing philosophy); 02 Request Lifecycle (full flow + Mermaid sequence diagram, cache hit/miss/error); 03 Pipeline (order, responsibilities, interactions, fail-open, context lifecycle, gating); 04 Provider Layer (abstraction, 3 providers, **response-normalization contract spec**); 05 Configuration (hierarchy, defaults, overrides, validation, extension strategy); 06 Metrics (ownership, propagation, routing_reason, routing_precedence, latency, cost); 07 **Architectural Contracts C1–C8** (normative guarantees + why + enforcement); 08 Extension Guide (provider/stage/metrics/config recipes, principles, approval rules); 09 Internal Assessment (Software Factory view + **ADB-11** internal architecture contracts, ADB-12 machine-readable manifest, ADB-13 normalization enforcement). ARCHITECTURE.md pointer + GOVERNANCE_INDEX KB registry + README pointer. **Validation**: Decision 24 paths, routing_reason fallback, metrics vocabulary, config groups cross-checked vs code; 29 md links + 31 inline paths resolve; examples untouched; suite 167 unchanged; CI green |

## IN PROGRESS

| Task | Notes |
|------|-------|
| (none) | M15 (release v0.1.0) next |

## BLOCKED

| Task | Blocked by | Unblocked by |
|------|------------|--------------|
| (none) | — | — |

## READY

| # | Task | Depends on |
|---|------|------------|
| M15 | Release v0.1.0: tag, notes, optional PyPI (⚠ publish) | M6–M14 |

## Blocked-by-approval backlog

- M15 (PyPI publish — optional)
- Merge Dependabot action-upgrade PRs (checkout/setup-python/upload-artifact
  → v7) — opened 2026-08-01, not blockers

## Resolved

- M12 deletions/archival — approved + executed 2026-08-01 (Decision 23)
- RouterStage complexity-fallback hole — **resolved 2026-08-01 by the
  routing precedence contract (Decision 24)**
