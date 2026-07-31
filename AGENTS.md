# AGENTS.md — AI Agent Operating Manual

> **Source of truth for every AI coding agent** working in this repository.
> This file is intentionally tool-agnostic: it applies to OpenCode, Claude Code,
> Cursor, GitHub Copilot, ChatGPT, Gemini, and any future coding agent.
>
> The binding constitution of this project is `.ai/PROJECT_MANIFEST.md`.
> Where this file and the manifest disagree, the manifest wins.

---

## Project

**TokenOpt SDK** (`tokenopt`) is a Python SDK that makes LLM interactions
cheaper, faster, and more context-efficient — as a **drop-in replacement** for
OpenAI, Anthropic, and local model servers.

Users change one import and get automatic optimization:

```python
# Before
from openai import OpenAI

# After
from tokenopt import OpenAI
```

Optimizations are performed by a configurable pipeline (routing, compression,
summarization, semantic caching, RAG and few-shot optimization), with built-in
metrics and structured logging.

- Language: Python ≥ 3.10
- Package: `tokenopt` (clients / pipeline / observability / utils)
- Providers: OpenAI, Anthropic, Ollama, vLLM, llama.cpp, LM Studio
- Tests: `pytest` · Lint: `ruff` · Types: `mypy`
- All project state lives in `.ai/` — treat it as authoritative memory.

---

## Agent Responsibilities

The AI agent is responsible for:

- **Architecture** — proposing and documenting design changes before
  implementing them; recording decisions in `.ai/DECISIONS.md`.
- **Implementation** — writing correct, typed, lint-clean code that follows
  repository conventions.
- **Testing** — adding or updating tests with every code change; keeping the
  suite green.
- **Documentation** — keeping code docstrings, `README.md`, and `.ai/` memory
  current with every change.
- **Version control** — committing work in small logical commits, never
  leaving completed work uncommitted or unpushed.
- **Project memory** — maintaining `CURRENT_STATE.md`, `NEXT_STEPS.md`,
  `SESSION_LOG.md`, `ROADMAP.md`, and `ARCHITECTURE.md`.
- **Checkpoints** — creating checkpoint files at every milestone so any future
  session (or model) can resume with full context.

---

## Startup Procedure

**Before writing any code**, read the following, in order:

1. `.ai/PROJECT_MANIFEST.md` — the constitution
2. `.ai/CURRENT_STATE.md` — what exists and what is in flight
3. `.ai/NEXT_STEPS.md` — what to work on next
4. `.ai/DECISIONS.md` — accepted architecture decisions (binding)
5. `.ai/ROADMAP.md` — where the project is heading
6. `.ai/ARCHITECTURE.md` — how the system is structured
7. `.ai/SESSION_LOG.md` — what previous sessions did
8. The most recent checkpoint in `.ai/CHECKPOINTS/` — where work left off
9. `.ai/SESSION_STATE.md` — live status (milestone, task, risk)
10. `.ai/TASK_QUEUE.md` — what is READY / IN PROGRESS / BLOCKED / DONE
11. `README.md` — the user-facing entry point

**Then, as applicable:**

- `.ai/STANDARDS/` — normative engineering rules (coding, documentation,
  testing, git, release, security, ai-memory, checkpoint). Read the ones
  relevant to the task before acting.
- `.ai/WORKFLOWS/` — follow the matching workflow (implement-feature,
  fix-bug, code-review, release, handover) when one applies.
- `.ai/ROLES/` — adopt the applicable role definition (architect,
  backend-engineer, reviewer, technical-writer) when the task demands it.

Only then begin implementation.

---

## Development Rules

- **Never begin coding before understanding the repository** and its state.
- **Never delete documentation** — docs are append-only assets.
- **Never remove or overwrite checkpoints** — always create new ones.
- **Never ignore failing tests** — a red suite is a blocked merge.
- **Never ignore lint failures** — zero `ruff` findings before commit.
- **Never change architecture without approval** (see Approval Gates).
- **Never change public APIs without approval** — the drop-in contract is sacred.
- **Never add dependencies without approval** — extras exist to avoid heavy
  defaults.
- **Never change package structure without approval** — `pyproject.toml`
  package layout is deliberate.
- **Never modify the Git remote or guess URLs** — verify `git remote -v`
  before every push and stop if it is missing or malformed.
- **Fail open** — optimization must never break the underlying request;
  stage errors downgrade, they do not fail the call.
- **Small focused changes** — one logical change per commit; no giant diffs.

---

## Documentation Rules

Whenever implementation changes, update as applicable:

- `.ai/CURRENT_STATE.md` — completed / in-progress work
- `.ai/SESSION_LOG.md` — what was done this session
- `.ai/NEXT_STEPS.md` — what remains, and what changed
- `.ai/ROADMAP.md` — if scope or phasing changed
- `.ai/ARCHITECTURE.md` — if structure or flows changed
- `.ai/DECISIONS.md` — when a new decision is made (append-only)
- `README.md` — if user-facing behavior changed

Code documentation: module and public API docstrings are mandatory; comments
explain *why*, never *what*.

---

## Git Rules

- Create **small, logical commits** — never one giant commit.
- Commit message format: `<type>: <summary>` where type is one of
  `feat`, `fix`, `refactor`, `docs`, `test`, `chore`.
- **Commit only after:**
  - tests pass (`pytest tests/`),
  - lint passes (`ruff check tokenopt tests`),
  - documentation is updated.
- **Push after every completed milestone.**
- **Never leave completed work only on the local machine.**
- Before any push: verify `git remote -v` matches
  `github.com/<username>/<repository>.git`; if not, stop and ask for approval.

---

## Checkpoint Rules

Create a checkpoint whenever:

- approximately 75% of the available context has been consumed, **or**
- a major feature or milestone completes, **or**
- switching models / agents, **or**
- ending a session.

Store checkpoints at:

```
.ai/CHECKPOINTS/CHECKPOINT_YYYYMMDD_HHMM.md
```

Each checkpoint must include:

- completed work
- modified files
- commit hashes
- blockers
- architecture decisions made
- next tasks
- an exact prompt to continue work in a new session

**Never overwrite previous checkpoints** — always create a new file.

---

## Approval Gates

**Stop and ask for approval before:**

- architecture changes
- dependency changes
- breaking public APIs
- package restructuring
- database / storage schema changes
- deployment changes

Do not continue until approval is received. When approval is granted, record
the decision in `.ai/DECISIONS.md` before implementing.

---

## Session Close Procedure

Before ending a session, in order:

1. Ensure `git status` is clean (all work committed).
2. Run the test suite (`pytest tests/`) — all green.
3. Run lint (`ruff check tokenopt tests`) — all clean. (Also `mypy` and
   `python -m build` when applicable; record failures, never hide them.)
4. Update project memory (CURRENT_STATE, NEXT_STEPS, SESSION_LOG,
   SESSION_STATE, TASK_QUEUE, and ROADMAP/ARCHITECTURE if necessary).
5. Create a checkpoint in `.ai/CHECKPOINTS/`.
6. Commit the memory and checkpoint changes.
7. Verify `git remote -v`, then push.
8. Confirm the push succeeded (branch up to date with `origin/main`).
9. Summarize the work completed for the user.
10. Stop and wait for the next session.

**Controlled shutdown (Decision 12):** stop EARLY — at milestone completion,
~40–60 substantial interactions, ~60–90 minutes elapsed, or any natural
stopping point. Never attempt to maximize context usage; one extra checkpoint
is always better than lost work. The repository — never the conversation — is
the single source of truth.

---

## Continuous Improvement

The agent should actively identify improvements to:

- architecture,
- documentation,
- workflow,
- testing,
- tooling.

**Propose improvements before implementing them** — surface the idea, the
rationale, and the expected benefit, then let the user decide. Approved
improvements become decisions recorded in `.ai/DECISIONS.md` and items in
`.ai/NEXT_STEPS.md`, and may be codified as new rules in `.ai/STANDARDS/`,
`.ai/WORKFLOWS/`, or `.ai/ROLES/`.

---

_Compliance with this manual is expected for every interaction with this
repository. When in doubt, read more of `.ai/` — not less._
