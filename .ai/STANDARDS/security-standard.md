# Security Standard

_Standard owner: `.ai/ROLES/security-engineer.md` (future) / reviewer_
_Related: `.ai/PROJECT_MANIFEST.md` §4, Decision 11_

## Scope

Secrets, logging, dependencies, remotes, and fail-open behavior.

## Rules

1. **Secrets** — never commit, log, print, or persist API keys, tokens, or
   credentials. Keys enter only via constructor params or environment.
2. **Logging hygiene** — structured logs must not contain keys, full prompts
   by default, or PII. Metrics callbacks never leak into the main flow
   (fail-open).
3. **Dependencies** — no unbounded `>=` for critical deps where possible;
   audit regularly with `pip-audit` (M7); review ranges at release time.
4. **Scanning** — secret scans (gitleaks/trufflehog) and dependency audits
   run locally and in CI (M7).
5. **Remote policy (Decision 11)** — never modify or guess the remote URL;
   verify `git remote -v` before every push; stop and ask if malformed.
6. **Fail open** — an optimization-stage error downgrades to a plain request;
   it never fails the call or leaks partial data.
7. **Supply chain** — review dependencies before adding (Approval Gate);
   prefer narrow extras (`cache`, `semantic`, `compression`, `local`) over
   heavy defaults.
8. **Configuration** — `TokenOptConfig` validation raises early on invalid
   values (fail fast at init, not mid-request).
9. **Rendering/parsing** — never eval untrusted prompt content; treat model
   output as data (no code execution).
10. **Reporting** — security findings are recorded in `.ai/CURRENT_STATE.md`
    and raised to the user immediately.

## Verification

```bash
pip-audit                                   # no known vulnerabilities (M7)
gitleaks detect --source .                  # no secrets (M7)
git remote -v                               # pattern check before push
```

## Incident response (for agents)

1. Stop the operation; do not push.
2. Report to the user with evidence (no secret material in the report).
3. Rotate/remove the exposed credential (user action).
4. Record the incident in `.ai/SESSION_LOG.md`; add a fix item to
   `NEXT_STEPS.md`.
