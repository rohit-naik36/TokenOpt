# Checkpoint Standard

_Standard owner: all agents (session continuity)_
_Related: `.ai/STANDARDS/ai-memory-standard.md`, AGENTS.md_

## Scope

Checkpoints are resumability snapshots: any future session, model, or agent
must be able to continue with full context from the latest checkpoint alone.

## When to create

Create a checkpoint when **any** of the following is true:

- approximately **75% of available context** has been consumed, **or**
- a **major feature or milestone** completes, **or**
- **switching models / agents / sessions**, **or**
- ending a session (mandatory at session close).

## Location and naming

```
.ai/CHECKPOINTS/CHECKPOINT_YYYYMMDD_HHMM.md
```

Example: `CHECKPOINT_20260801_0056.md`. Timestamps are local time.

## Required content

1. **Milestone** — one-line title of what this checkpoint closes.
2. **Completed work** — bullets, outcome-focused.
3. **Modified files** — list of paths touched.
4. **Commits** — hashes (short) of relevant commits.
5. **Remaining work** — next tasks, ordered.
6. **Blockers** — anything blocking progress, and who/what unblocks it.
7. **Decisions made** — new or reaffirmed decisions (link to DECISIONS.md).
8. **Verification status** — test/lint/build results at checkpoint time.
9. **Next prompt** — an exact, copy-pasteable prompt to resume work.

## Rules

1. **Never overwrite** — always create a new file; prior checkpoints stay
   forever (append-only asset).
2. **Never delete** — checkpoints are part of project memory and history.
3. **Commit with the work** — the checkpoint is committed and pushed in the
   same milestone as the work it summarizes.
4. **Accuracy over brevity** — a checkpoint missing verification status is
   not a checkpoint.

## Template

```markdown
# CHECKPOINT_YYYYMMDD_HHMM

## Milestone: <title>

## Completed work
- ...

## Modified files
- ...

## Commits
- <hash> <message>

## Remaining work
1. ...

## Blockers
- ...

## Decisions made
- ... (see DECISIONS.md)

## Verification status
- pytest: ...
- ruff: ...
- build: ...

## Next prompt
"<exact resume prompt>"
```
