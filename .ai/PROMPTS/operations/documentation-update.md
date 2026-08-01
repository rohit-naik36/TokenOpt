# Prompt: Documentation Update

_Group: operations_
_Related: `.ai/WORKFLOWS/documentation-update.md`; owner: `.ai/ROLES/technical-writer.md`_
_Standards: documentation, ai-memory, git_

## Objective

Keep documentation accurate and current — README, CHANGELOG, docstrings,
and `.ai/` memory — in the same commit as the change it describes (or as a
standalone `docs:` correction when docs drift). Documentation derives from
reality, never aspiration.

## Required inputs

- The change set or drift report (stale README, broken link, missing
  docstring, memory gap)
- Affected doc inventory (README sections, CHANGELOG, `.ai/` state files,
  GOVERNANCE_INDEX registry)

## Instructions (deterministic)

1. Identify the affected documentation surface; read the current content
   before editing.
2. Verify every claim against code: run the command, read the code, check
   the config defaults — do not document behavior you did not verify.
3. Apply documentation-standard: module + public API docstrings mandatory;
   comments explain *why*, never *what*; README is the user entry point.
4. CHANGELOG: `[Unreleased]` → Added/Changed/Fixed/Removed entries per
   release-standard; keep the exact wording style of existing entries.
5. Update `.ai/` memory as applicable (CURRENT_STATE, SESSION_LOG,
   NEXT_STEPS); flag stale memory as a defect (bug-fix prompt).
6. Fix broken links; keep cross-references per `.ai/GOVERNANCE_INDEX.md`.
7. Verify no broken links in changed files; for touched Python files:
   ```bash
   ruff check <changed files>
   ```
8. Commit `docs: <summary>` in the same commit as the code change when
   possible; otherwise a standalone `docs:` commit. Push after verifying
   `git remote -v` (Decision 11).

## Expected outputs

- Updated docs + CHANGELOG entries
- Fresh `.ai/` memory
- `docs:` commit + push

## Verification criteria

- [ ] Every claim spot-verified against code/output
- [ ] No broken relative links
- [ ] CHANGELOG follows release-standard format
- [ ] Memory current
- [ ] Committed + pushed

## Determinism rules

- Never document a feature as "coming soon" unless it exists in code.
- When a doc claim and code disagree, the code wins — fix the doc.
