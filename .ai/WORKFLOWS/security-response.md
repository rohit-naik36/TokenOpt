# Workflow: Security Response

_Owner: `.ai/ROLES/security-reviewer.md`; user escalation for scope decisions_
_Standards: security, testing, git, release; related: `.ai/SECURITY.md`, `.ai/DOD.md`_

## Purpose

Respond to a security report or finding (SECURITY.md disclosure, gitleaks /
pip-audit / Dependabot alert, or a user report) with severity-appropriate
speed, a fix, and a release classification — blocker or advisory.

## Prerequisites

- A report or scanner finding exists (see SECURITY.md for supported
  versions and reporting channels).
- Classify severity first: **blocker** (secrets, auth bypass, data
  exposure, RCE) vs **advisory** (best-practice, tooling, dependency
  hygiene).

## Steps

1. **Triage** — severity + affected components; confirm reproduction.
2. **Contain** — blockers: stop the bleeding first (rotate leaked secrets,
   disable affected path, pin vulnerable dep) — user approval for
   disruptive actions.
3. **Fix** — smallest root-cause fix per fix-bug workflow; secrets never
   enter the repo; scanner findings get a regression check.
4. **Verify** — full gates + the relevant scanner:
   ```bash
   pytest tests/ -q
   ruff check tokenopt tests
   mypy tokenopt
   pip-audit --path .          # dependency findings
   gitleaks detect --log-opts=--all   # secret findings
   ```
5. **Release decision** — blocker → expedite a PATCH release (release
   workflow; user approval for publish); advisory → tracked in NEXT_STEPS
   with a deadline.
6. **Disclose** — coordinate per SECURITY.md (90-day window, private
   reporting honored); note in CHANGELOG without exposing details
   pre-disclosure.
7. **Document** — incident record in SESSION_LOG, findings in NEXT_STEPS;
   update SECURITY.md if scope/process gaps were exposed.

## Expected outputs

- Severity classification + incident record
- Fix (blocker) or tracked advisory with deadline
- Release classification applied

## Completion criteria

- [ ] Blocker: fixed, verified, release decision made and executed
- [ ] Advisory: recorded in NEXT_STEPS with deadline
- [ ] Scanners clean after fix
- [ ] Disclosure timeline honored
