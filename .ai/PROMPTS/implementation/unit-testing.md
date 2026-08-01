# Prompt: Unit Testing

_Group: implementation_
_Related: `.ai/STANDARDS/testing-standard.md`; owner: `.ai/ROLES/qa-engineer.md` (strategy), `.ai/ROLES/backend-engineer.md` (writing)_
_Standards: testing, coding, git_

## Objective

Write deterministic unit tests for a module that pin behavior contracts,
cover edge cases and error paths, and keep the ≥ 80% coverage gate honest.

## Required inputs

- The module under test (`tokenopt/<module>.py`) and its public surface
- Existing tests for conventions (`tests/test_<module>.py`)
- `.ai/STANDARDS/testing-standard.md` and `INTEGRATION_TEST_STRATEGY.md`
  (what belongs in unit vs integration)

## Instructions (deterministic)

1. Read the module and its dependencies; list every public function/class
   and branch worth pinning (documented behavior, config switches, error
   paths, fail-open).
2. Follow existing test conventions: `test_<behavior>` names, fixtures
   from `conftest.py`, provider fakes via `httpx.MockTransport` for any
   I/O — NO network in unit tests.
3. For each behavior write exactly one test that asserts the observable
   contract; include: edge cases (empty input, malformed content,
   boundary token counts) and the fail-open path (stage error → request
   still succeeds).
4. Never assert on timing values except broad bounds; never use
   `time.sleep` to fake determinism.
5. Verify the tests fail meaningfully: temporarily break the behavior
   under test (or use the pre-fix code for a bug test) and confirm the
   test fails; restore.
6. Run the module's tests plus the full suite:
   ```bash
   pytest tests/test_<module>.py -q
   pytest tests/ -q
   ```
7. Check coverage for the module; report the module percentage vs the
   ≥ 80% suite gate.
8. Commit `test: <behavior covered>` (or fold into the feature/fix commit
   per that workflow); push after verifying `git remote -v` (Decision 11).

## Expected outputs

- `tests/test_<module>.py` (extended) with deterministic tests
- Per-module coverage report
- `test:` commit or test-included feature/fix commit

## Verification criteria

- [ ] Every listed behavior has a test
- [ ] Tests are deterministic (run 3× → same result)
- [ ] No network access in unit tests
- [ ] Suite green; coverage gate ≥ 80% maintained
- [ ] Tests fail without the behavior (proven at least once)

## Determinism rules

- Tests must be order-independent and parallel-safe.
- Assert on behavior, never on implementation internals unless the
  contract requires it.
