# CLAUDE.md - TokenOpt (Claude Code entry point)

`AGENTS.md` and `.ai/` remain the project constitution and memory. This file only adds the Claude Code layer. Where they disagree, `AGENTS.md` / `.ai/PROJECT_MANIFEST.md` win.

## Current mission
Streamline TokenOpt into one demoable result for a solutions architect on SDLC agent workloads (coding, tests, CI output, diffs, plans): fewer tokens at >=95% fidelity vs an uncompressed baseline, measured per category on real traces, reproducible in one command. The 40% target is a goal, not a claim: existing research shows low single-digit gains for generic compression on coding traces. Plan and prompt: `.claude/PROMPT_STREAMLINE.md`. Live state: `.claude/HANDOFF.md`.

## Start of every session (token-light order)
1. Run `/resume` (reads `.claude/HANDOFF.md` and `git status`, nothing else).
2. Open only the `.ai/` / KB files the current task needs (map: `.ai/KNOWLEDGE_BASE/README.md`). Do not bulk-read `.ai/`.
3. The repo is the fact; the KB is a snapshot. If they disagree, stop and report.

## Agents (`.claude/agents/`)
cto (scope, cuts) · principal-architect (design) · fullstack-dev (build, test-first) · qa-eval-engineer (benchmark, judge, gate) · security-reviewer · demo-lead (README, DEMO.md) · repo-auditor (cleanup audit). Each maps to a role in `.ai/ROLES/`.

## Hard rules
- No LiteLLM layer, in any form.
- Never delete. Archive per `.ai/REPOSITORY_RETENTION_POLICY.md`, and only after the user approves the list.
- Architecture, API or dependency changes and `.ai/DECISIONS.md` entries need the user's approval. Draft them; do not write them unapproved.
- Do not push, and do not switch branches with uncommitted changes, without asking.
- Report measured numbers only (`.ai/KNOWLEDGE_BASE/12_EVIDENCE_BOUNDARY.md`). Misses are reported, not hidden.
- Never commit secrets; keys come from environment variables.
- Done-gate: `ruff check tokenopt tests`, `mypy tokenopt`, `pytest tests -q`, with real output pasted.

## End of every task
Run `/handoff` (one line in Done, refresh Now/Next). At milestones, also run the `.ai/WORKFLOWS/handover.md` workflow so `.ai/` memory stays current.
