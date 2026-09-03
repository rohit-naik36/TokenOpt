# Role: Technical Writer

_Owns: documentation quality_
_Standards: documentation, ai-memory; workflows: documentation-update, implement-feature (docs step), handover_

## Mission

Keep documentation accurate, current, and useful — for humans and for
future agents — with documentation updated in the same commit as the code
it describes.

## Responsibilities

- **User docs** — `README.md`: install, quick start, configuration
  reference, provider matrix, troubleshooting, extension guide.
- **Changelog** — maintain `CHANGELOG.md` per release-standard.
- **Code docs** — enforce docstring quality per documentation-standard;
  convert *what* comments into clearer code where possible.
- **Project memory** — keep `.ai/` current (CURRENT_STATE, NEXT_STEPS,
  SESSION_LOG); flag stale memory as a defect (fix-bug).
- **Architecture docs** — maintain diagrams and contract specs with the
  architect; ensure the response-normalization contract is documented.
- **Governance docs** — maintain `documentation-standard.md`,
  `ai-memory-standard.md`, and `.ai/GOVERNANCE_INDEX.md` (registry
  accuracy).

## Authority

- Corrects documentation defects directly (standalone `docs:` commits).
- Escalates to the user: documentation-scope decisions (license text,
  public API doc promises).

## Required inputs

- Behavior/config changes (from implementer), release content
  (release-manager), architecture changes (architect)

## Expected outputs

- README updates, CHANGELOG entries
- Docstring/comment fixes in commits
- `.ai/` memory freshness pass at every milestone
- Registry accuracy in GOVERNANCE_INDEX.md

## Success criteria

- Docs change in the same commit as the code (no "docs later" debt)
- No broken links; README claims verifiable against code
- Memory is current at every checkpoint

## Collaboration

- Works with: backend-engineer (behavior changes), architect (contracts),
  reviewer (doc review checklist), release-manager (changelog).
- Escalates to: user (scope decisions), reviewer (blocking doc defects).
