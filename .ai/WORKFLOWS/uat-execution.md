# Workflow: UAT Execution

_Owner: `.ai/ROLES/qa-engineer.md`; sign-off recorded per release_
_Standards: testing, documentation, git; related: `docs/UAT.md`, `.ai/DOD.md`_

## Purpose

Execute the manual acceptance checklist against a realistic environment
before a milestone or release closes — confirming the drop-in contract
works the way users will actually use it.

## Prerequisites

- Milestone/release candidate exists; `main` is green (CI).
- Environment ready: clean venv (`pip install -e .`) + offline stub server
  (`%TEMP%/opencode/m8-stub/stub_server.py`) or a live endpoint the user
  provides.
- `docs/UAT.md` checklist current for the change set.

## Steps

1. **Prepare** — fresh venv, env vars (keys + base URLs for the stub),
   start the stub; note versions (Python, package).
2. **Execute** — walk `docs/UAT.md` scenario groups in order (env, install,
   quick start, per-provider, cache, routing, metrics, errors, cleanup);
   record each checkbox with the actual observed output.
3. **Run examples** — all `examples/*.py` exit 0; printed metrics are
   truthful vs the recorded metrics (M8.2 standard).
4. **Log defects** — failures become fix-bug items with reproduction
   commands; annotate the checklist (pass / fail / skipped + why).
5. **Sign off** — pass: sign-off line in the checklist + SESSION_LOG;
   fail: blocking items back to the owner, UAT repeats after fixes.
6. **Memory** — UAT results noted in CURRENT_STATE / SESSION_LOG.

## Verification

```bash
python -m pytest tests/ -q          # automated gate still required
# + manual: python examples/<name>.py per checklist
```

## Expected outputs

- Completed `docs/UAT.md` checklist with observed evidence
- Defect list (if any) with reproduction steps
- Sign-off or "blocked, re-run needed" verdict

## Completion criteria

- [ ] Every applicable scenario executed and recorded
- [ ] All examples exit 0 (or failures logged as defects)
- [ ] Verdict recorded (pass / blocked)
- [ ] Defects routed via fix-bug with a re-run plan
