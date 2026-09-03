# AI Memory Standard

_Standard owner: all agents (memory is shared)_
_Related: `.ai/PROJECT_MANIFEST.md` §8, `.ai/STANDARDS/documentation-standard.md`_

## Scope

The `.ai/` directory is the authoritative, durable memory of the project —
what exists, what's next, what was decided, what happened, where work left off.

## Files

| File | Purpose | Update cadence |
|------|---------|----------------|
| `PROJECT_MANIFEST.md` | Constitution (rarely changes; revision bump + approval) | Approval only |
| `CURRENT_STATE.md` | What exists / in flight | Every milestone & session close |
| `NEXT_STEPS.md` | What to do next (task queue) | When scope/state changes |
| `DECISIONS.md` | Accepted decisions (append-only) | When a decision is approved |
| `ROADMAP.md` | Phasing and long-term direction | When scope/phasing changes |
| `ARCHITECTURE.md` | Structure, flows, contracts | When architecture changes |
| `SESSION_LOG.md` | Chronological record of sessions | Every session |
| `CHECKPOINTS/` | Resumability snapshots | Per checkpoint rules |
| `REPOSITORY_AUDIT.md` | Health baseline (read-only) | On re-audit |
| `SESSION_STATE.md` | Live status: milestone, task, progress, stopping point, risk | Every session (especially shutdown) |
| `TASK_QUEUE.md` | Task board: READY / IN PROGRESS / BLOCKED / DONE | When tasks change |

## Rules

1. **Authoritative** — `.ai/` beats chat context when they disagree; read
   before coding (AGENTS.md startup procedure).
2. **Append-only** — decisions and checkpoints are never edited or deleted;
   supersede by adding new entries.
3. **Freshness** — "Last updated" dates are kept current; stale memory is a
   defect, fix it in the same session that caused the staleness.
4. **One source of truth** — avoid duplicating facts across files; reference
   the owning file instead (e.g. NEXT_STEPS points to ROADMAP for phasing).
5. **Session log format** — `## YYYY-MM-DD — Session N: <title>` followed by
   a bulleted Work performed section and context links.
6. **Decisions** — record: decision, rationale, status. Never rewrite a
   previous row; a new row supersedes.
7. **Memory is code-adjacent** — memory updates are committed with the work
   they describe (same milestone, same push).
8. **Session state** — `SESSION_STATE.md` holds the live status (milestone,
   task, progress, safe stopping point, remaining work, context risk) and is
   updated at every session end or controlled shutdown.
9. **Task queue** — `TASK_QUEUE.md` is the task board; move items between
   READY / IN PROGRESS / BLOCKED / DONE as work progresses.
10. **Controlled shutdown (Decision 12)** — when stopping early (milestone
    done, ~40–60 interactions, ~60–90 min elapsed, natural stopping point):
    stop production code, validate (pytest/ruff/mypy/build — record failures),
    update ALL memory files, create a checkpoint, update SESSION_STATE +
    TASK_QUEUE, commit, push, hand over, and stop.

## Definition of "memory updated"

A milestone is not complete until: `CURRENT_STATE.md` reflects the work,
`SESSION_LOG.md` has the entry, and `NEXT_STEPS.md` shows what remains.
