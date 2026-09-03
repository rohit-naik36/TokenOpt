# Workflow: Dependency Upgrade

_Owner: `.ai/ROLES/devops-engineer.md`, reviewed by `.ai/ROLES/security-reviewer.md`_
_Standards: security, testing, git, release; related: `.ai/DOD.md`_

## Purpose

Upgrade or add a dependency safely: assess impact, keep gates green, and
avoid the failure modes that pinned numpy `>=1.24,<2.5` (Python/mypy
incompatibility) and required the optional-extras mypy overrides.

## Prerequisites

- A driver exists: Dependabot PR, `pip-audit` finding, security advisory,
  or a feature requirement.
- **New dependencies require user approval** (Approval Gates) before
  implementation.

## Steps

1. **Triage** — classify: patch (safe), minor (check), major (approval +
   careful review), security advisory (expedite via security-response).
2. **Impact check** — target Python ≥ 3.10; mypy compatibility (stubs,
   PEP 695); extras not pulled into the core install unless approved;
   transitive dependency changes.
3. **Test** — upgrade in a clean env; run full gates (Verification); run
   `pip-audit` on the result.
4. **Review** — reviewer + security-reviewer confirm: no unbounded ranges
   introduced, no CVEs in the result, extras unchanged.
5. **Dependabot** — for automated PRs, run the same checks; merge only on
   green; configure ignores for known-bad pins (e.g. numpy ≥ 2.5).
6. **Document** — `CHANGELOG.md` under `Changed` when runtime deps change;
   CONTRIBUTING / README extras tables if install instructions change.
7. **Commit + push** — `chore: bump <dep> to <version>` (git-standard);
   verify remote (Decision 11).

## Verification

```bash
pytest tests/ -q
ruff check tokenopt tests
mypy tokenopt
pip-audit --path .
```

## Expected outputs

- Dependency change with green gates
- pip-audit clean (or documented, approved exceptions)
- Changelog/memory entries

## Completion criteria

- [ ] Gates green after upgrade
- [ ] pip-audit clean
- [ ] No new core dependency without user approval
- [ ] Python 3.10–3.12 matrix still green (CI)
- [ ] Committed + pushed
