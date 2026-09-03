# Workflow: Regression Verification

_Owner: `.ai/ROLES/qa-engineer.md`_
_Standards: testing, git; related: uat-execution, dependency-upgrade, release; `.ai/DOD.md`_

## Purpose

Prove that past behavior still holds after a change — a fast, deterministic
sweep before release, after dependency upgrades, or when CI is unstable.
Complements (does not replace) the automated gate.

## Prerequisites

- A change set exists (commit range, release candidate, or dependency bump).
- Suite is green at HEAD; baseline commit identified for comparison.

## Steps

1. **Select scope** — commit range since the last green run (or the last
   release); list touched modules.
2. **Full gate** — clean checkout, run everything:
   ```bash
   pytest tests/ -q
   ruff check tokenopt tests
   mypy tokenopt
   ```
3. **Coverage check** — confirm the ≥ 80% coverage gate holds and coverage
   did not drop vs baseline.
4. **Known-defect sweep** — re-run the regression tests that pin past
   defects (CHANGELOG `Fixed` entries, DECISIONS-marked defects) for the
   touched area.
5. **Example sweep** — `examples/*.py` against the stub server (see
   uat-execution) when behavior or metrics changed.
6. **Report** — verdict: no regression / regression with failing items;
   failing items get reproduction + a fix-bug entry.

## Expected outputs

- Regression verdict with evidence (commands, outputs)
- Coverage comparison vs baseline
- Regression defect list routed to fix-bug

## Completion criteria

- [ ] Full gate green at the candidate commit
- [ ] Coverage ≥ baseline (≥ 80% gate)
- [ ] Past-defect tests re-run for the touched area
- [ ] Verdict recorded in SESSION_LOG; blockers routed
