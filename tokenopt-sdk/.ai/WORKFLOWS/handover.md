# Workflow: Handover / Session Close

_Owner: all agents (mandatory at session end)_
_Standards: ai-memory, checkpoint, git, documentation_
_Related: `.ai/DOD.md`; controlled shutdown (Decision 12)_

## Purpose

Guarantee the repository — never the conversation — is the complete source
of truth when a session, model, or agent ends. Any future agent resumes
from the repo alone.

## Prerequisites

- A natural stopping point: milestone complete, ~40–60 interactions,
  ~60–90 minutes elapsed (Decision 12: stop EARLY), or the user ends the
  session.

## Steps (in order)

1. **Commit everything** — `git status` clean; no half-finished work left
   uncommitted (logical commits, never one giant commit).
2. **Run verification**
   ```bash
   pytest tests/ -q
   ruff check tokenopt tests
   mypy tokenopt
   ```
3. **Update project memory** — CURRENT_STATE (completed/in-flight/blocked),
   NEXT_STEPS (what remains, ordered), SESSION_LOG (`## YYYY-MM-DD —
   Session N: <title>`), SESSION_STATE, TASK_QUEUE; ROADMAP/ARCHITECTURE/
   DECISIONS only if they changed.
4. **Create checkpoint** — `.ai/CHECKPOINTS/CHECKPOINT_YYYYMMDD_HHMM.md`
   per checkpoint-standard (milestone, work, files, commits, blockers,
   decisions, verification, next prompt). Never overwrite prior checkpoints.
5. **Commit memory + checkpoint** — `docs:` commit.
6. **Push** — verify `git remote -v` (Decision 11); push; confirm the
   branch is up to date with `origin/main`.
7. **Summarize** — tell the user what was completed and what is next.
8. **Stop** — wait for the next session.

## Expected outputs

- Clean tree, green gates, current memory
- New checkpoint + memory commit pushed
- Completion summary for the user

## Completion criteria

- [ ] `git status` clean
- [ ] Tests + lint + mypy green
- [ ] Memory updated
- [ ] Checkpoint created (new file, never overwritten)
- [ ] Pushed and confirmed
- [ ] Summary delivered; agent idle
