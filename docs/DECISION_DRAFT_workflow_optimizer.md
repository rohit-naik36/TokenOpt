# DRAFT decision (NOT in `.ai/DECISIONS.md`; needs user approval)

## D-NEW: Workflow-level optimizer as an ingress package, outside the canonical pipeline
Date: 2026-10-10. Status: PROPOSED.

**Decision:** Add `tokenopt/handoff/` (router, <=4 handlers, gate, in-memory recall store, ledger). It compresses each new tool result once at ingress via `compress_segment(text, kind)`; compressed text becomes canonical history. It does not run inside `CanonicalOptimizer`, `execution.py` or the proxy in v1.

**Why:** The existing pipeline marks tool payloads P0/no-compress, reprocesses full history each call, and can roll back earlier messages, which breaks prefix caching. Ingress-once is prefix-stable by construction. Prose compression measured ~0.9% on real agent prompts; structured tool output is the only plausible large lever.

**Contract change requested:** carve-out in `architecture/context-preservation-contract.md` allowing lossy, recoverable compression of tool output via the handoff path only, with protected-fact checks and recall handles.

**New surface:** package `tokenopt/handoff/`, config flags (default off), `tokenopt_recall` tool (registered from turn 0), trace schema `agent-trace/v2` (optional workflow_id, parent_workflow_id, agent, step). No change to the tracked v1 doc.

**Not doing:** LiteLLM, ML models, key aliasing, history rewriting, proxy persistence stack.

**Gates:** handler protected-fact retention >=99%, never larger, idempotent, deterministic; end-to-end outcome >=95% of baseline on held-out 30%; misses reported. Target 30-40% is unproven.

**Open:** proxy path is not a valid host until streaming flatten (tokenopt_proxy_v2.py:770-776) and `_normalize_message` field-dropping (execution.py:43-56) are fixed; separate decision.

**Licenses:** rtk, headroom Apache-2.0; repomix MIT (likely). Study only unless attribution/NOTICE handled.
