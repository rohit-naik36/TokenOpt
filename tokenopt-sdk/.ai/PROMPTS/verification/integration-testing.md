# Prompt: Integration Testing

_Group: verification_
_Related: `.ai/WORKFLOWS/implement-feature.md` (test step); `INTEGRATION_TEST_STRATEGY.md`; owner: `.ai/ROLES/qa-engineer.md` (strategy), `.ai/ROLES/backend-engineer.md` (writing)_
_Standards: testing, coding, git_

## Objective

Verify cross-component behavior through the client surface — the full
optimization pipeline end to end — with zero new dependencies and fully
offline execution.

## Required inputs

- The feature/behavior being integrated (NEXT_STEPS item or diff)
- `INTEGRATION_TEST_STRATEGY.md` (offline policy, provider isolation,
  determinism rules)
- Existing integration fixtures (`tests/integration/conftest.py` —
  `httpx.MockTransport` handlers)

## Instructions (deterministic)

1. Read `INTEGRATION_TEST_STRATEGY.md`; confirm the change is integration-
   level (spans ≥ 2 components: pipeline stage → client → metrics) vs
   unit-level (unit-testing prompt instead).
2. Map the flow under test: routing → compression → summarization →
   caching → RAG/few-shot → API call → metrics recording.
3. Add a test in `tests/integration/` using `httpx.MockTransport` via
   `http_client=` (Decision 15) — no new dependencies, no live network.
4. Assert observable outcomes: request body actually sent (recorded by the
   transport), cache short-circuit (N identical calls → 1 provider call),
   metrics fields populated, error paths (provider 500 re-raised + error
   metrics recorded), fail-open (stage exception downgraded).
5. Verify:
   ```bash
   pytest tests/integration/ -q
   pytest tests/ -q
   ```
6. Commit `test: <integrated behavior>` (or fold into the feature commit);
   push after verifying `git remote -v` (Decision 11).

## Expected outputs

- Integration test(s) in `tests/integration/`
- Recorded-request evidence (assertions on the transported body)

## Verification criteria

- [ ] Offline (MockTransport only, no real endpoints)
- [ ] No new dependencies (Decision 15 budget intact)
- [ ] Full suite green
- [ ] Deterministic across runs

## Determinism rules

- Fake time and random; never depend on wall clock.
- Assert request shape, not order of dict keys.
