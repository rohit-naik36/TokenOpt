# Workflow: Repository Audit

_Owner: `.ai/ROLES/repository-auditor.md`_
_Standards: all (evidence-based scoring); related: `.ai/REPOSITORY_AUDIT.md`, `.ai/DOD.md`_

## Purpose

Periodically re-assess repository health against the audit categories and
produce an evidence-based improvement plan — the refresh loop that keeps
the baseline audit (`REPOSITORY_AUDIT.md`) from going stale. Curation
(deletions/archives) follows `.ai/REPOSITORY_RETENTION_POLICY.md`.

## Prerequisites

- A trigger: milestone completion, quarterly cadence, or a major structure
  change.
- Read the previous audit as the baseline.
- Read the retention policy (`REPOSITORY_RETENTION_POLICY.md`) before any
  deletion or archive action.

## Steps

1. **Inventory** — snapshot structure, docs, gates, CI, tooling; note
   additions since the last audit (e.g. security scans, examples, M8.2).
2. **Score** — re-run the audit categories with evidence (tests, coverage,
   CI state, lint/type status, doc freshness, security posture).
3. **Find gaps** — new weaknesses get severity + effort estimates; confirm
   old findings closed (evidence, not assumption).
4. **Update** — refresh `REPOSITORY_AUDIT.md` scores and the prioritized
   improvement plan; keep history (append a dated section, never rewrite
   evidence).
5. **Curation** — classify changes against `REPOSITORY_RETENTION_POLICY.md`;
   delete only regenerated/disposable entries, archive historical ones
   (`git mv` to `.ai/ARCHIVE/`), escalate anything else; update
   `REPOSITORY_INVENTORY.md` ledger.
6. **Route** — improvements become NEXT_STEPS / TASK_QUEUE items with
   owners (by role) and dependencies; approval-gated items flagged.
7. **Commit + push** — `docs: update repository audit` (git-standard);
   verify remote (Decision 11).

## Verification

- Every score traceable to a command or file in this repo.
- No improvement item without an owner and a next step.
- Retention policy consulted for every deletion/archive; ledger current.

## Expected outputs

- Updated audit with dated evidence
- Prioritized improvement plan routed to NEXT_STEPS / TASK_QUEUE
- (Curation passes) updated inventory + retention-policy disposition log

## Completion criteria

- [ ] Categories re-scored with evidence
- [ ] Old findings confirmed closed or re-opened
- [ ] New items routed with owners
- [ ] Committed + pushed
