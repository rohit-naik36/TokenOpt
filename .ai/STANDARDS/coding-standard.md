# Coding Standard

_Standard owner: `.ai/ROLES/architect.md` + `.ai/ROLES/backend-engineer.md`_
_Related: `.ai/PROJECT_MANIFEST.md` §4_

## Scope

Applies to all Python code in `tokenopt/`, `tests/`, and `examples/`.

## Rules

1. **Python version** — target ≥ 3.10; use modern syntax (`X | None`, builtin
   generics) but stay compatible with 3.10.
2. **Type hints** — required on all function/method signatures (public and
   private). `Any` is allowed only where provider SDKs are inherently dynamic.
3. **Lint gate** — `ruff check tokenopt tests` must report **zero findings**
   before any commit. Rules: `E, F, I, UP, W`, line length 100.
4. **Type gate** — `mypy tokenopt` must exit 0 (verified as part of M1; the
   numpy pin and optional-extras overrides live in `pyproject.toml`).
5. **Naming** — classes `PascalCase`; functions/methods/variables
   `snake_case`; constants `UPPER_SNAKE`; private helpers prefixed `_`.
6. **Imports** — absolute imports, sorted (isort via ruff), stdlib first,
   then third-party, then local.
7. **Comments** — explain *why*, never *what*. If code needs a "what" comment,
   the code should be rewritten. Module and public API docstrings are mandatory.
8. **Module size** — prefer modules under ~300 lines; extract shared helpers
   rather than duplicating (see `MODEL_COSTS` data-module pattern).
9. **Fail open** — optimization-stage errors must never break the underlying
   request; catch, downgrade, and continue.
10. **No secrets in code** — API keys only from caller/environment; never log,
    print, or persist them.
11. **Config-driven behavior** — no hidden flags; everything configurable
    through `TokenOptConfig` (or explicit constructor params).
12. **Drop-in contract** — never break the wrapped provider API surface
    without approval (Decision-class change).

## Verification

```bash
ruff check tokenopt tests        # zero findings
mypy tokenopt                    # exit 0 (after M1 fix)
pytest tests/ -q                 # all green
```

## Conventions quick reference

| Item | Convention |
|------|------------|
| Files/dirs | `snake_case.py` |
| Pipeline stages | `CompressorStage` + lowercase `name` attribute |
| Test files | `test_<module>.py` |
| Test functions | `test_<behavior>` |
| Commit types | `feat fix refactor docs test chore` |
