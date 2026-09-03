# AI Prompt Library — TokenOpt

_Last updated: 2026-08-01_
_Owner: `.ai/ROLES/technical-writer.md`; registry: `.ai/GOVERNANCE_INDEX.md`_
_Purpose: reusable, deterministic instruction sets for AI-assisted engineering — the operational layer of the Idea → Software Factory._

## What this library is

Each file in this library is a **self-contained prompt**: the exact
instruction set an agent (or human) applies to a defined task. Prompts are
grouped by purpose, not by provider or chronology, so the right prompt is
findable in one step.

## Grouping

| Group | Purpose | Prompts |
|-------|---------|---------|
| `design/` | decisions about structure and contracts | architecture-review |
| `implementation/` | producing or changing code | feature, bug-fix, refactoring, unit-testing |
| `verification/` | proving behavior holds | integration-testing, regression-verification |
| `operations/` | keeping the system truthful and releasable | documentation-update, release-preparation, repository-audit |

## Prompt template

Every prompt MUST contain exactly these sections, in order:

1. **Objective** — what the prompt achieves, one or two sentences.
2. **Required inputs** — the minimum inputs; a prompt without defined
   inputs is not usable by an autonomous agent.
3. **Instructions (deterministic)** — numbered steps; each step is a
   concrete action (exact command, exact file path, exact checklist).
4. **Expected outputs** — the artifacts produced (files, verdicts,
   commits).
5. **Verification criteria** — checkboxes; each is executable or
   observable, never subjective.
6. **Determinism rules** — explicit "never/always" constraints that remove
   judgment calls.

Plus a header block: `_Group:`, `_Related:` (workflow link), `_Owner:`
(role link), `_Standards:` — for machine resolution via GOVERNANCE_INDEX.

## Deterministic-execution rules (design principles)

- **Exact commands** — verification uses the repo's real commands
  (`pytest tests/ -q`, `ruff check tokenopt tests`, `mypy tokenopt`),
  never "run the tests".
- **Exact paths** — every referenced file is a full relative path
  (`.ai/WORKFLOWS/fix-bug.md`), never "the workflow file".
- **Evidence over memory** — prompts require recorded command output,
  never recalled results.
- **Fail-open preserved** — any prompt touching optimization code keeps
  the fail-open invariant (errors downgrade, never fail the request).
- **One judgment-call limit** — if a step requires interpretation, the
  prompt says what to do when uncertain (e.g. "report back with evidence
  instead of guessing").
- **Composable** — prompts reference each other by path for handoffs
  (e.g. release-preparation → uat-execution), matching the workflow
  handoff map.

## Cross-references

- Every prompt links its governing **workflow** (`.ai/WORKFLOWS/`) and
  owning **role** (`.ai/ROLES/`) and the relevant **standards**
  (`.ai/STANDARDS/`).
- `.ai/GOVERNANCE_INDEX.md` is the registry that resolves task → workflow
  → role → prompt.
- A prompt is the *execution* layer; the workflow is the *runbook*; the
  role is the *ownership*; the standard is the *normative rule*. Keep
  them in that relationship — no duplication of rules across layers.

## Adding a prompt

1. Follow the template above exactly.
2. Place it in the matching purpose group; create the group if none fits
   (update the Grouping table here).
3. Add its row to `.ai/GOVERNANCE_INDEX.md`.
4. Reference it from its related workflow (Handoff section) if the
   workflow benefits.
5. A new prompt is only "live" after being used once against a real task
   or explicitly accepted by the user — record which in
   `.ai/SESSION_LOG.md`.

## Maintenance rule

- Never delete a prompt (append-only, like checkpoints).
- A prompt that fails determinism (ambiguous step) is a defect: fix via
  the documentation-update prompt.
- Review the library for dead prompts at each repository audit.
