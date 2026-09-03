# Governance Index — TokenOpt

_Last updated: 2026-08-01_
_Owner: `.ai/ROLES/technical-writer.md`; verified by `.ai/ROLES/repository-auditor.md`_
_Purpose: the machine-consumable registry for the AI engineering operating system — the first reusable component of the Idea → Software Factory._

Entry point for agents: on task start, resolve the task → workflow →
owning role via the tables below, then read the referenced file(s).

## Roles (11)

| Role | Owns | Primary workflows |
|------|------|-------------------|
| product-strategist | product vision, roadmap direction | repository-audit (input) |
| product-manager | requirements, backlog clarity | implement-feature (pre-work) |
| architect | architecture decisions, technical strategy | architecture-review, code-review, release |
| backend-engineer | implementation quality | implement-feature, fix-bug, refactoring, performance-investigation |
| reviewer | change validation | code-review |
| qa-engineer | test strategy, acceptance execution | uat-execution, regression-verification |
| security-reviewer | security posture | security-response, dependency-upgrade |
| technical-writer | documentation quality | documentation-update, handover |
| release-manager | release process, versioning | release |
| devops-engineer | CI, tooling, dependency hygiene | dependency-upgrade |
| repository-auditor | repository health assessment | repository-audit |

## Workflows (14)

| Workflow | Owner | Review authority | Use when |
|----------|-------|------------------|----------|
| implement-feature | backend-engineer | reviewer | a scoped feature item is ready |
| fix-bug | backend-engineer | reviewer | a defect is reported/reproduced |
| refactoring | backend-engineer | reviewer | behavior-preserving structure change |
| code-review | reviewer | (self) | a change needs the done-gate |
| architecture-review | architect | user (gates) | architecture/API decisions |
| documentation-update | technical-writer | reviewer | docs drift or follow a change |
| dependency-upgrade | devops-engineer | security-reviewer | Dependabot PR, CVE, pin review |
| security-response | security-reviewer | user (disclosure) | vulnerability report/finding |
| performance-investigation | backend-engineer | architect | latency/cost concern |
| uat-execution | qa-engineer | release-manager (sign-off) | pre-release acceptance |
| regression-verification | qa-engineer | release-manager (sign-off) | release / dep-upgrade / CI flakiness |
| repository-audit | repository-auditor | product-manager (routing) | milestone/quarterly health check |
| release | release-manager | architect (arch impact) | a release milestone or hotfix |
| handover | all agents (mandatory) | (self) | session/model switch or end |

## Standards (8)

coding, documentation, testing, git, release, security, ai-memory,
checkpoint — `.ai/STANDARDS/` (normative detail of manifest §4).

## Prompts (10)

`.ai/PROMPTS/` — execution-layer instruction sets (grouped by purpose).

| Prompt | Group | Owned by | Governed by workflow |
|--------|-------|----------|----------------------|
| architecture-review | design | architect | architecture-review |
| feature | implementation | backend-engineer | implement-feature |
| bug-fix | implementation | backend-engineer | fix-bug |
| refactoring | implementation | backend-engineer | refactoring |
| unit-testing | implementation | qa-engineer (strategy) | testing-standard |
| integration-testing | verification | qa-engineer (strategy) | INTEGRATION_TEST_STRATEGY.md |
| regression-verification | verification | qa-engineer | regression-verification |
| documentation-update | operations | technical-writer | documentation-update |
| release-preparation | operations | release-manager | release |
| repository-audit | operations | repository-auditor | repository-audit |

Design rules: `.ai/PROMPTS/README.md` (template + determinism rules).

## Policies (2)

| Policy | Owner | Governs |
|--------|-------|---------|
| `.ai/REPOSITORY_RETENTION_POLICY.md` | repository-auditor | what is permanent / archived / regenerated / disposable; deletion gate |
| `.ai/REPOSITORY_INVENTORY.md` | repository-auditor | classified inventory + deletion ledger (companion to the policy) |

## Knowledge Base (M14)

`.ai/KNOWLEDGE_BASE/` — the permanent architecture knowledge base
(documented 2026-08-01, M14; docs-only, no runtime change). Owned by
`architect` (content) + `technical-writer` (freshness); consumed by all
roles, AI agents, and future Software Factory orchestration systems.

| Doc | Content | Normative for |
|-----|---------|---------------|
| `README.md` | index + reading order | every agent on task start |
| `01_SYSTEM_OVERVIEW.md` | goals, philosophies, package structure | onboarding |
| `02_REQUEST_LIFECYCLE.md` | full request flow incl. Mermaid | implement-feature, fix-bug |
| `03_PIPELINE.md` | stage order, responsibilities, fail-open, context | refactoring, performance-investigation |
| `04_PROVIDER_LAYER.md` | provider abstraction + normalization contract | adding providers (C6/C8) |
| `05_CONFIGURATION.md` | config ownership, defaults, validation | configuration changes (C7) |
| `06_METRICS.md` | metrics ownership + vocabulary | metrics changes (C5) |
| `07_ARCHITECTURAL_CONTRACTS.md` | C1–C8 guarantees (normative) | architecture-review gate |
| `08_EXTENSION_GUIDE.md` | provider/stage/metrics/config recipes | contributors |
| `09_INTERNAL_ASSESSMENT.md` | strengths, limitations, ADB-11..13 | roadmap/audit input |

Change rule: KB-07 contracts are normative; changing one requires the
architecture-review workflow + user approval. Documentation updates follow
the documentation-update workflow.

## Ownership matrix (no conflicts)

| Area | Sole owner |
|------|-----------|
| Vision/roadmap direction | product-strategist |
| Requirements/backlog | product-manager |
| Architecture + public API stability | architect |
| Code implementation | backend-engineer |
| Change validation (done-gate) | reviewer |
| Test strategy + acceptance | qa-engineer |
| Security posture + incidents | security-reviewer |
| Documentation + memory freshness | technical-writer |
| Releases/versioning/tags | release-manager |
| CI/tooling/dependencies process | devops-engineer |
| Health audits + improvement routing | repository-auditor |

## Approval gates (single escalation path)

Every workflow escalates through the same gate — **the user**:
architecture, public API, dependencies, package structure, storage schema,
deployment, deletions, PyPI publish.

## Handoff map

```
idea/request ─► product-strategist ─► product-manager ─► (scope)
      ─► backend-engineer (implement-feature / fix-bug / refactoring)
      ─► reviewer (code-review) ─► qa-engineer (uat-execution /
          regression-verification) ─► release-manager (release) ─► user
arch:  ─► architect (architecture-review) ─► user (approval)
sec:   ─► security-reviewer (security-response) ─► user (disclosure)
deps:  ─► devops-engineer (dependency-upgrade) ─► security-reviewer
audit: ─► repository-auditor (repository-audit) ─► product-manager
every session: ─► handover (all agents)
```
