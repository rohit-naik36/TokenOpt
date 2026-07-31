# Workflow: Handover / Session Close

_Owner: all agents (mandatory at session end)_
_Standards: ai-memory, checkpoint, git, documentation_

## Trigger

Ending a session, switching models/agents, or context running low
(~75% consumed).

## Steps (in order)

1. **Commit everything** — `git status` clean; no half-finished work left
   uncommitted (commit in logical units; never one giant commit).
2. **Run verification**
   ```bash
   pytest tests/ -q
   ruff check tokenopt tests
   ```
3. **Update project memory**
   - `CURRENT_STATE.md` — completed/in-flight/blocked
   - `NEXT_STEPS.md` — what remains, ordered
   - `SESSION_LOG.md` — session entry (`## YYYY-MM-DD — Session N: <title>`)
   - `ROADMAP.md` / `ARCHITECTURE.md` / `DECISIONS.md` only if they changed
4. **Create checkpoint** — `.ai/CHECKPOINTS/CHECKPOINT_YYYYMMDD_HHMM.md`
   per checkpoint-standard (commits, blockers, decisions, verification,
   next prompt). Never overwrite prior checkpoints.
5. **Commit memory + checkpoint** — `docs:` commit.
6. **Push** — verify `git remote -v` (Decision 11); push; confirm success
   (branch up to date with `origin/main`).
7. **Summarize** — tell the user what was completed and what is next.
8. **Stop** — wait for the next session.

## Exit criteria

- [ ] `git status` clean
- [ ] Tests + lint green
- [ ] Memory updated
- [ ] Checkpoint created (new file, never overwritten)
- [ ] Pushed and confirmed
- [ ] Summary delivered; agent idle
