# CHECKPOINT 2026-08-01 — M12 Repository Curation

**Milestone:** M12 — Repository Curation
**Status:** DONE (curation only; SDK untouched)
**Decision:** 23 (see `.ai/DECISIONS.md`)

## Completed work

- **Inventory + classification** (`.ai/REPOSITORY_INVENTORY.md`): every
  root + sub-tree entry classified — active governance / generated
  artifact / duplicate / historical archive / future reference /
  user-owned — with a dated deletion ledger.
- **Deleted (approved scope — duplicates + regenerated only)**:
  - 7 empty artifact dirs: `C?ProjectsNew/`, `Idea_Factory/`,
    `Projecttests/`, `Projecttokenoptclients/`,
    `Projecttokenoptobservability/`, `Projecttokenoptpipeline/`,
    `Projecttokenoptutils/`
  - generated: `dist/`, `tokenopt.egg-info/`, `.coverage`,
    `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, 8× `__pycache__/`
- **Archived**: `SESSION_BACKUP.md` → `.ai/ARCHIVE/SESSION_BACKUP.md`
  via `git mv` (rename detected; history intact) — audit finding 9 closed.
- **Created `.ai/REPOSITORY_RETENTION_POLICY.md`**: five dispositions
  (permanent / archived / regenerated / disposable / user-owned),
  rules (deletion gate, append-only `.ai/`, archive-not-delete, curation
  procedure, disposition log).
- **Added GitHub templates**: `PULL_REQUEST_TEMPLATE.md`,
  `ISSUE_TEMPLATE/bug_report.md`, `ISSUE_TEMPLATE/feature_request.md`,
  `CODEOWNERS` (`* @rohit-naik36` — single-maintainer posture).
- **Updated governance**: REPOSITORY_AUDIT.md §7 dated closure (findings
  6 + 9, plan item 8 → closed; evidence-based, history preserved);
  GOVERNANCE_INDEX → Policies section (2 policies, owner
  repository-auditor); repository-audit workflow → curation step +
  retention-policy prerequisite.
- **Kept**: `docs/UAT.md` (active governance, referenced by qa-engineer
  role + uat-execution workflow), all `.ai/` memory, `TEST.txt`
  (user-owned scratch file — untouched).

## Modified files

- `.ai/REPOSITORY_INVENTORY.md` (new)
- `.ai/REPOSITORY_RETENTION_POLICY.md` (new)
- `.ai/ARCHIVE/SESSION_BACKUP.md` (moved)
- `.github/PULL_REQUEST_TEMPLATE.md`, `.github/ISSUE_TEMPLATE/{bug_report,feature_request}.md`, `.github/CODEOWNERS` (new)
- `.ai/REPOSITORY_AUDIT.md` (§7 closure)
- `.ai/GOVERNANCE_INDEX.md` (Policies section)
- `.ai/WORKFLOWS/repository-audit.md` (curation step)
- `.ai/DECISIONS.md` (+23), `.ai/CURRENT_STATE.md`, `.ai/SESSION_LOG.md`,
  `.ai/SESSION_STATE.md`, `.ai/NEXT_STEPS.md`, `.ai/TASK_QUEUE.md`

## Commit hashes

- `de3dc17` — `docs: add repository retention policy and inventory`
  (includes rename SESSION_BACKUP.md → `.ai/ARCHIVE/SESSION_BACKUP.md` —
  deletions of untracked/gitignored artifacts need no commit)
- <pending> — `docs: add GitHub PR and issue templates and codeowners`
- <pending> — `docs: close repository audit findings in dated section`
- <pending> — `chore: update memory and checkpoint for M12`

## Blockers

None. **Open decision before M13**: RouterStage complexity fallback
(custom routing rules with no match rewrite model to `gpt-*`; fix changes
OpenAI routing behavior — needs user decision).

## Architecture decisions made

- Decision 23: repository retention policy (five dispositions, deletion
  gate, archive-not-delete, git history never rewritten)

## Next tasks

1. M13 — maintainability refactor (behavior-preserving): response
   helpers, data-driven MODEL_COSTS (after RouterStage decision)
2. M14 — architecture docs polish (Mermaid, normalization spec,
   extension guide)
3. M15 — release v0.1.0 (tag, notes, optional PyPI ⚠)

## Exact prompt to continue in a new session

> M12 (Repository Curation) is complete: `.ai/REPOSITORY_INVENTORY.md` +
> `.ai/REPOSITORY_RETENTION_POLICY.md` created; 7 empty artifact dirs and
> all generated artifacts (dist/, egg-info, caches, .coverage,
> __pycache__) deleted; `SESSION_BACKUP.md` archived to
> `.ai/ARCHIVE/SESSION_BACKUP.md` (git mv, history intact); GitHub PR/
> issue templates + CODEOWNERS added; REPOSITORY_AUDIT §7 dated closure
> (findings 6 + 9, plan item 8 closed); GOVERNANCE_INDEX Policies
> section; DECISIONS +23; memory + this checkpoint updated; commits
> pushed to main (verify `git log` + CI badge passing). Root tree
> contains only intentional entries; suite 158 green.
> Continue with **M13** (maintainability refactor — behavior-preserving:
> response helpers, data-driven MODEL_COSTS) — but FIRST obtain the
> user's decision on the **RouterStage complexity fallback** (custom
> routing rules with no match rewrite model to `gpt-*`; affects OpenAI
> routing behavior). Follow `.ai/IMPLEMENTATION_ROADMAP.md`, the
> refactoring workflow (`.ai/WORKFLOWS/refactoring.md`) + owner role,
> AGENTS.md gates (pytest 158, ruff, mypy), then update memory, create
> CHECKPOINT_20260801_M13.md, commit, push (verify remote =
> https://github.com/rohit-naik36/TokenOpt.git), confirm CI green.
> Curation rules live in `.ai/REPOSITORY_RETENTION_POLICY.md`.
