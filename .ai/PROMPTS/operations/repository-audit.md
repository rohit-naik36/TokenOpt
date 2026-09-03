# Prompt: Repository Auditing

_Group: operations_
_Related: `.ai/WORKFLOWS/repository-audit.md`; owner: `.ai/ROLES/repository-auditor.md`_
_Standards: all (evidence-based scoring); baseline: `.ai/REPOSITORY_AUDIT.md`_

## Objective

Re-assess repository health with evidence, update the audit baseline, and
route every finding to an owned improvement item — every score traceable
to a command or file, never a vibe.

## Required inputs

- Previous audit (`.ai/REPOSITORY_AUDIT.md`) as baseline
- Milestone history (`.ai/SESSION_LOG.md`, checkpoints) since last audit
- Gate outputs: CI state, suite/coverage, lint/type, scanner results

## Instructions (deterministic)

1. Inventory: `git log --oneline <last audit commit>..HEAD`, file tree,
   `.ai/` structure, CI workflow, extras/tooling.
2. Re-score the audit categories with evidence. For each score record the
   exact command + output or file path:
   - tests: `pytest tests/ -q` (count + coverage)
   - lint/types: `ruff check tokenopt tests`, `mypy tokenopt`
   - CI: latest run conclusion (badge or API)
   - security: `pip-audit --path .`, `gitleaks detect --log-opts=--all`
   - docs/governance: link check over `.ai/**/*.md` (all resolve)
3. Compare with the baseline: confirm old findings closed (evidence),
   re-open stale ones, add new weaknesses with severity + effort.
4. Update `.ai/REPOSITORY_AUDIT.md` — append a dated section with the new
   evidence; never rewrite historical evidence.
5. Route every improvement: item → owner role (per
   `.ai/GOVERNANCE_INDEX.md` ownership matrix) → NEXT_STEPS/TASK_QUEUE
   with dependencies; approval-gated items flagged (⚠).
6. Commit `docs: update repository audit`; push after verifying
   `git remote -v` (Decision 11).

## Expected outputs

- Updated audit with dated evidence section
- Improvement plan routed with owners and dependencies

## Verification criteria

- [ ] Every score has a command/output or file-path citation
- [ ] Old findings confirmed closed or re-opened with evidence
- [ ] No improvement item without an owner + next step
- [ ] Baseline history preserved (append-only)

## Determinism rules

- Re-run the commands yourself; never reuse stale outputs.
- If a category cannot be scored, record "not scored" + reason — do not
  extrapolate.
