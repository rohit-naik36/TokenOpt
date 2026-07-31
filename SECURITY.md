# Security Policy

TokenOpt processes LLM API traffic and user prompts, so security is treated
as a first-class, continuously verified property — not a release-time event.
This policy defines the supported surface, the reporting process, and how
findings are classified as **release blockers** versus **advisories**.

## Supported Versions

| Version | Supported | Notes |
|---------|-----------|-------|
| `0.1.x` | ✅ | Current release line; security fixes land in the next `0.1.x` |
| `< 0.1.0` | ❌ | Pre-release development, no commitments |
| `main` branch | ✅ (development) | Maintained with the same security gates as releases |

Security fixes are backported to the current minor release line. TokenOpt is
pre-1.0 (Alpha): API and behavior may change between releases without
deprecation warnings, but security fixes are prioritized like any release
blocker.

## Vulnerability Reporting

**Do not open public issues for suspected vulnerabilities.** Report privately:

1. **GitHub Private Vulnerability Reporting** (preferred):
   open `https://github.com/rohit-naik36/TokenOpt/security/advisories/new`
2. **Email fallback**: send details to the maintainer via the GitHub profile
   listed in the repository metadata.

Include, when possible:

- Affected package version and Python version
- Whether the issue is in `tokenopt` itself, a runtime dependency, or the
  CI/packaging setup
- Reproduction steps or a minimal example
- Any exploit details (or your plan to disclose them)

The maintainer will acknowledge within **7 days** and send a resolution
timeline within **14 days**.

## Security Scope

**In scope:**

- The `tokenopt` package: client wrappers, pipeline stages, caching,
  observability, and utilities shipped in the sdist/wheel.
- Dependency vulnerabilities in the **runtime dependency set**
  (`dependencies` in `pyproject.toml`), as reported by `pip-audit` against
  the OSV advisory database.
- Secrets or credentials accidentally committed to the repository
  (`gitleaks` scan, full history).
- CI workflow configuration (`.github/`) — third-party action tampering,
  privilege escalation, or secret leakage through logs/artifacts.

**Out of scope / responsibility of the user:**

- API keys and credentials used **by** TokenOpt at runtime — these are the
  user's responsibility (e.g., OpenAI/Anthropic keys). TokenOpt fails open
  and never persists them beyond the calling process.
- Vulnerabilities in **optional extras** that are not installed by default
  (`redis`, `sentence-transformers`, `llmlingua`, `ollama`). These are
  scanned as advisories but are only exploitable if the user opts in.
- Misuse of the library (e.g., logging prompts containing secrets).
- Vulnerabilities in the user's own deployment, prompt content, or
  application code.

## Finding Classification

| Severity | Category | Example | CI behavior |
|----------|----------|---------|-------------|
| **Release blocker** | Critical/High runtime-dep vulnerability with a known exploit path on a supported Python version | `pip-audit` critical in `openai` | `pip-audit` step fails; release is blocked until upgraded or a mitigation is documented |
| **Release blocker** | Committed secret/credential | API key in git history | `gitleaks` step fails; secret must be **rotated** and history purged |
| **Advisory** | Medium/Low runtime-dep vulnerability without an active exploit path | OSV low in a transitive dep with no public exploit | CI passes with a tracked exception or documented mitigation |
| **Advisory** | Dev-only tool vulnerability | vuln in `pytest`, `ruff`, `mypy`, `pip-audit` itself | CI passes; fixed on the next scheduled Dependabot update |
| **Advisory** | Optional-extra vulnerability (not in default install) | vuln in `ollama` when `[local]` is unused | CI passes; fix tracked in the issue queue |

**Policy in practice:** every release must pass the full CI security job
(`pip-audit` + `gitleaks`) with **zero release-blocker findings**. Advisory
findings are tracked in the issue queue and reviewed at each milestone; they
do not block release unless they escalate to release-blocker criteria.

## Automated Verification (CI)

The `security` job in `.github/workflows/ci.yml` runs on every push to
`main` and every pull request:

- `pip-audit --path .` — audits the resolved runtime dependency set against
  the OSV database; any known vulnerability fails the job.
- `gitleaks detect --log-opts=--all` (pinned 8.30.1) — scans the full git
  history for secrets; any leak fails the job.

Additionally, **Dependabot** (`.github/dependabot.yml`) opens weekly update
PRs for `pip` dependencies and GitHub Actions, so dependency fixes arrive
continuously rather than only at release time.

## Disclosure Policy

- **Private reporting** — advisories are accepted privately and triaged per
  the timeline above; reporters are credited in the changelog unless they
  request anonymity.
- **Coordinated disclosure** — fixes are developed privately, committed as
  security fix(es), and announced in the CHANGELOG at the release where the
  fix ships.
- **Public disclosure** — after a fix is released, details may be published
  (in the advisory or changelog) **90 days** after the reporter was first
  contacted, or immediately if a public exploit exists — whichever is
  earlier.
- **No bug bounty** — this project does not offer monetary rewards; reports
  are acknowledged publicly in the changelog.

## Security Checklist for Contributors

- Never commit real credentials; use environment variables or generated
  test keys only.
- Keep generated test keys scoped to test-only services.
- Run `pip-audit` and `gitleaks` locally before pushing (both run in CI
  anyway).
- Follow the git and review rules in `CONTRIBUTING.md`; never force-push to
  `main`.
