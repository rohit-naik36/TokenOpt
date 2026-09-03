# Prompt: Regression Verification

_Group: verification_
_Related: `.ai/WORKFLOWS/regression-verification.md`; owner: `.ai/ROLES/qa-engineer.md`_
_Standards: testing, git; handoff to: release-preparation, dependency-upgrade_

## Objective

Prove past behavior still holds at a candidate commit — full gate,
coverage comparison, past-defect sweep, and example sweep — producing a
recorded no-regression verdict with evidence.

## Required inputs

- Candidate commit range (since last green run or release tag)
- Baseline green state + last release/checkpoint reference
- Past-defect inventory (CHANGELOG `Fixed` entries, DECISIONS-marked
  defects)

## Instructions (deterministic)

1. Determine the change set: `git log <baseline>..HEAD --oneline`; list
   touched modules.
2. Clean checkout or clean env; run the full gate:
   ```bash
   pytest tests/ -q
   ruff check tokenopt tests
   mypy tokenopt
   ```
3. Capture coverage and compare to baseline: must not drop below ≥ 80%.
4. Re-run regression tests for past defects in the touched area
   (unit + integration); each must pass.
5. If behavior or metrics changed, sweep examples against the stub server
   (`.ai/WORKFLOWS/uat-execution.md`): every `examples/*.py` exits 0 and
   printed explanations match recorded metrics.
6. Record the verdict with evidence: **NO REGRESSION** or
   **REGRESSION** + failing items with reproduction commands.
7. Route failures via `implementation/bug-fix.md`; report blockers to the
   release-manager if this is release-scoped.

## Expected outputs

- Verdict with commands/output evidence
- Coverage comparison (baseline vs candidate)
- Defect list routed to bug-fix

## Verification criteria

- [ ] Full gate green at the candidate commit
- [ ] Coverage ≥ baseline (≥ 80% gate)
- [ ] Past-defect tests re-run for the touched area
- [ ] Examples exit 0 (when behavior/metrics changed)
- [ ] Verdict recorded in SESSION_LOG

## Determinism rules

- Evidence is commands + output, never memory.
- If any gate is red, the verdict is REGRESSION — do not proceed to
  release without a fix.
