# Repository Retention Policy — TokenOpt

_Last updated: 2026-08-01 (M12 — Repository Curation)_
_Owner: `.ai/ROLES/repository-auditor.md`; enforced by the
repository-audit workflow and the governance approval gate (deletions
escalate to the user)._

## Categories

| Category | Rule | Examples |
|----------|------|----------|
| **Permanent** | Never delete, move, or rewrite. Append-only. Changes are additions or corrections with a dated note. | `.ai/` governance (memory, standards, workflows, roles, prompts, checkpoints, decisions, audits, policies), SDK `tokenopt/`, `tests/`, `examples/`, README, CHANGELOG, LICENSE, SECURITY, CONTRIBUTING, `docs/UAT.md`, CI + Dependabot config, pyproject.toml, Makefile, AGENTS.md, INTEGRATION_TEST_STRATEGY.md |
| **Archived** | Retained for historical value when superseded or no longer current. Moves to `.ai/ARCHIVE/` via `git mv` (history preserved). Never deleted outright. | `SESSION_BACKUP.md` (superseded by `.ai/` memory; archived 2026-08-01) |
| **Regenerated** | Safe to delete at any time; produced on demand by tooling. Keep out of git (`.gitignore`). | `dist/`, `*.egg-info/`, `.coverage`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `__pycache__/` |
| **Disposable** | Accidental or redundant entries with no value; delete in curation passes. | empty artifact directories (e.g. the 7 mangled-path dirs removed 2026-08-01) |
| **User-owned** | Never touched by agents; the user manages it. | `TEST.txt` (scratch file) |

## Rules

1. **Deletion requires documented reason + approval.** Deletions of
   anything not in the Regenerated or Disposable category escalate
   through the single approval gate (the user) per Decision 21 / the
   governance index.
2. **Git history is permanent.** Files are moved, never force-removed;
   no history rewriting (`git rebase`/`filter-branch`) without explicit
   user approval.
3. **Archive, don't delete, when future value is plausible.** When a
   document is superseded, move it to `.ai/ARCHIVE/` with a dated note
   in the inventory rather than deleting it.
4. **`.ai/` is append-only.** Checkpoints are never overwritten; audits
   record dated closures instead of rewriting findings.
5. **Regenerated artifacts are cleaned in curation passes** (M12 +
   periodic repository audits) but never tracked.
6. **Every curation pass updates** the inventory (this policy's
   companion) with a dated deletion ledger.

## Procedure (curation pass)

1. Inventory the root tree and sub-trees (`.ai/`, `.github/`, docs).
2. Classify each entry against the table above.
3. Delete only Regenerated + Disposable entries; archive Historical
   ones; escalate anything else.
4. Update `.ai/REPOSITORY_INVENTORY.md` (classification + ledger).
5. Verify: link check, SDK/tests untouched, gates green, git history
   intact.
6. Commit (`chore:` / `docs:`), push (remote verified, Decision 11),
   CI green, checkpoint.

## Disposition log

| Date | Item | Disposition |
|------|------|-------------|
| 2026-08-01 | `SESSION_BACKUP.md` | archived → `.ai/ARCHIVE/` |
| 2026-08-01 | `dist/`, `tokenopt.egg-info/`, `.coverage`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, 8× `__pycache__/` | deleted (regenerated) |
| 2026-08-01 | `C?ProjectsNew/`, `Idea_Factory/`, `Projecttests/`, `Projecttokenoptclients/`, `Projecttokenoptobservability/`, `Projecttokenoptpipeline/`, `Projecttokenoptutils/` | deleted (disposable empty dirs) |
