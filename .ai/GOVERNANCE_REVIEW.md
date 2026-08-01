# Governance Review — M10 (AI Engineering Governance Expansion)

_Last updated: 2026-08-01_
_Owner: `.ai/ROLES/repository-auditor.md`; produced via `.ai/WORKFLOWS/repository-audit.md`_

## Scope

Reviewed all governance artifacts: `.ai/WORKFLOWS/` (5), `.ai/ROLES/` (4),
`.ai/STANDARDS/` (8), `AGENTS.md`, `.ai/PROJECT_MANIFEST.md`,
`.ai/IMPLEMENTATION_ROADMAP.md`, `.ai/ROADMAP.md`, `.ai/DECISIONS.md`, and
the `.ai/CHECKPOINTS/` system.

## Phase 1 — Findings

### Duplication (acceptable or fixed)

| Finding | Verdict |
|---------|---------|
| Verification commands repeated in every workflow | **Accepted** — self-contained runbooks are a feature for autonomous agents (no cross-file lookups mid-task) |
| `release.md` re-states items of `release-standard.md` | **Accepted** — runbook vs normative standard distinction; release.md delegates explicitly |
| Approval-gate wording repeated in AGENTS.md, manifest, workflows | **Accepted** — the gates are the single safety invariant; repetition is deliberate |

### Inconsistencies (fixed in this milestone)

| # | Finding | Fix |
|---|---------|-----|
| I1 | `implement-feature.md` step 6 says "(mypy after M1 fix.)" — **stale** (M1 shipped long ago; mypy is mandatory) | All workflows now run the same gate: `pytest tests/ -q` + `ruff check tokenopt tests` + `mypy tokenopt` |
| I2 | Verification blocks differ per workflow (some lack `mypy`) | Unified verification section in every workflow |
| I3 | `release.md` owner = "maintainer + architect" — no maintainer role exists | Owner → `.ai/ROLES/release-manager.md` (+ architect for arch review) |
| I4 | `fix-bug.md` header omits the `checkpoint` standard | Header standards list aligned |
| I5 | Workflows do not reference `.ai/DOD.md` (the ratified Definition of Done) | Every workflow now links DOD as the completion authority |
| I6 | `ROADMAP.md` Phase 0 counts ("5 runbooks", "4 role definitions") would drift | Counts updated (14 workflows, 11 roles) |
| I7 | `IMPLEMENTATION_ROADMAP.md` M10 described a pre-execution scope | M10 entry updated to the executed scope (user-approved) |
| I8 | Workflow/role registries existed only implicitly | `.ai/GOVERNANCE_INDEX.md` added as the machine-consumable registry |

### Missing workflows (added, 9)

refactoring, architecture-review, documentation-update, dependency-upgrade,
security-response, performance-investigation, uat-execution,
regression-verification, repository-audit.

### Missing roles (added, 7)

product-strategist, product-manager, qa-engineer, security-reviewer,
release-manager, devops-engineer, repository-auditor.

### Not changed (no value in rewriting)

- `.ai/STANDARDS/` — complete, internally consistent, actively used.
- `.ai/PROJECT_MANIFEST.md` — constitution; references remain valid;
  changes require user approval by its own terms.
- Checkpoint system — consistent with `checkpoint-standard.md`; no gaps.
- `AGENTS.md` startup procedure — still accurate; only the WORKFLOWS/ROLES
  pointers were updated to the new registry.

## Phase 4 — Validation (multi-agent composability)

| Check | Result |
|-------|--------|
| Circular responsibilities | None — each owned area has exactly one owning role (see GOVERNANCE_INDEX.md matrix) |
| Conflicting ownership | None — `reviewer` (change validation) vs `qa-engineer` (test strategy/UAT) vs `security-reviewer` (security posture) scoped explicitly; collaboration sections document the boundaries |
| Missing approval gates | None — every workflow escalates through the same single gate: the user (Approval Gates in AGENTS.md) |
| Deterministic execution order | All workflows have numbered steps + explicit verification + completion criteria |
| Clear handoffs | Every workflow names its owning role and review role; the workflow→role map is in GOVERNANCE_INDEX.md |
| Gaps identified | None blocking; noted follow-ups: M11 PROMPTS (optional), per-workflow usage stats after 3 milestones |

## Phase 5 — Documentation quality

- Unified templates: all 14 workflows and 11 roles share one structure.
- Cross-references: workflows → owner role, review role, standards, DOD;
  roles → workflows + interacting roles; index links everything.
- Link check: every `.ai/*.md` relative reference verified resolvable.
- No SDK code, tests, or public API touched (pure governance/documentation).

## Deliverables

- 9 new workflows + 5 rewritten (unified template)
- 7 new roles + 4 rewritten (extended template)
- `.ai/GOVERNANCE_INDEX.md` (registry + ownership matrix)
- This review summary
- Roadmap / implementation-roadmap / AGENTS.md reference updates
