# Testing Standard

_Standard owner: `.ai/ROLES/qa-engineer.md` (future) / reviewer_
_Related: `.ai/PROJECT_MANIFEST.md` §4, §7_

## Scope

All automated verification: unit, integration, coverage, CI.

## Rules

1. **Framework** — `pytest` (`asyncio_mode = "auto"`, `testpaths = ["tests"]`).
2. **No network in unit tests** — provider calls are faked (subclassing,
   mock clients, HTTP stubs). Tests must run offline and fast (< 30 s).
3. **Naming** — files `test_<module>.py`; functions `test_<behavior>`;
   describe intent, not implementation.
4. **Coverage gate** — ≥ **80% line coverage** for `tokenopt/` (configured in
   `[tool.coverage]`; enforced by pytest `--cov` + CI). New code must not
   lower module coverage below target.
5. **Test tiers**
   - **Unit** (`tests/`): single stage/module in isolation, deterministic.
   - **Integration** (`tests/integration/`): full client flow against
     stubbed servers — optimize → call → cache → metrics; error paths;
     cache-hit short-circuit.
6. **Behavior over implementation** — assert on outcomes (responses, metrics,
   cache entries), not on internal call counts unless behavior requires it.
7. **Error paths are first-class** — every fail-open path (stage exception)
   and provider-error path must have a test.
8. **Timing** — never assert exact timings; use broad bounds or disable.
9. **New features require tests** — a feature without tests is not done
   (Definition of Done, manifest §7).
10. **Keep the suite green** — a red suite blocks commit and merge; never
    disable tests silently (only with approval + recorded reason).

## Verification

```bash
pytest tests/ -q                          # all green
pytest tests/ --cov=tokenopt --cov-report=term   # coverage report
```

## Acceptance criteria for a new test suite

- [ ] Runs offline
- [ ] No timing assertions
- [ ] Exercises the fail-open path where one exists
- [ ] Coverage contribution visible in the report
