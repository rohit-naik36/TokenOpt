# Design: workflow-level token optimizer (v1 proposal)

Status: APPROVED IN PRINCIPLE, **BUILD DEFERRED (not cancelled)**. Date: 2026-10-10.

**Why deferred (Phase 1b census, `experiments/sdlc_census/REPORT.md`, no model calls):**
- Aegis bug-fix controls (1 task, 30 sessions): test/CI output is 5.0-5.8% of weighted cost, file reads 2.6-4.0%, JSON/logs and diffs 0 (absent). All context levers combined at 100% removal = 7.6-9.8% weighted. Output is 44-45% of cost, one average turn 12-15%.
- opencode read-only analysis (2 sessions): file reads 68% of weighted cost, cache-prefix breaks 22.2% pooled; small sample, no outcome label, outlines changed decisions in prior tests.
- Multi-agent handoff bloat: unmeasured; a nested-workflow trace is being generated (`experiments/nested_trace/`). Handlers (H1-H4), proxy fixes and the handoff package are not built until that result and the user's decision.
The measured ceiling for handlers alone on bug-fix work is below the 25-30% target even at 100% removal; the sections below describe the design that would be built if the nested trace or a read-heavy workload justifies it.

## 1. Goal and metric
Cut tokens by 30-40% across a whole multi-agent SDLC workflow (including nested sub-workflows), measured end to end: sum of provider-reported tokens over every model call, plus weighted cost. Quality gate: end-to-end outcome (repo tests pass, final artifact judged) >= 95% of baseline. This is a target to test, not a claim. Prior evidence: generic prose compression ~1% on real agent prompts; context compression low single digits on single-agent coding traces; large wins only on structured or repetitive tool output.

## 2. Where it sits
Interposer at the model-call boundary of the user's own pipeline (SDK, optional proxy). Two hook points:
1. Ingress: new content entering context (tool results, logs, diffs, files) is classified and compressed once, at arrival.
2. Workflow boundary: when an agent or nested workflow hands off, it returns a typed contract, not a transcript.
Invariant: append-only and prefix-stable. Earlier messages are never rewritten (rewriting breaks provider prompt caching and can raise cost).

## 3. Components
| Component | Job | Reuse |
|---|---|---|
| Router | Classify each segment (test output, JSON/log, diff, code, prose, unknown) with a confidence; unknown or low confidence = pass through | New, small, in `tokenopt/handoff/`. NOT `analyzer.py`: it hard-codes `role=="tool"` as P0/no-compress (analyzer.py:43-44, 397-406) and has no test/log/diff types |
| Handlers | One small file each; compress a segment of one type | New `tokenopt/handoff/handlers/` |
| Gate | Protected-fact check, never-larger check, ladder (aggressive -> conservative -> passthrough), fail-open | New. Reuse only `extract_invariants()` (analyzer.py:268) and the marker check (validator.py:631) plus SDLC patterns (file:line, test ids, exit codes). `validator.py` has no ladder or never-larger check and reverts non-JSON tool content (221-231) |
| Recall store | Every lossy cut gets an opaque content-hash handle to the original; `tokenopt_recall(handle)` | New, in-memory dict scoped to one workflow; no file paths as handles; per-workflow recall budget; redaction reused from `execution_trace.py` |
| Cache guard | Asserts previously sent bytes are unchanged between turns; deterministic and idempotent output | New tests + runtime assert (byte hash of prefix incl. `tools`) |
| Ledger | Records workflow_id, parent_workflow_id, agent, step, provider usage per call; hierarchical roll-up | `agent-trace/v1` is only a doc (`experiments/agent_benchmark/TRACE_SCHEMA.md`) and excludes sub-agent linkage (line 57): define `v2` as optional fields, test with `replay_trace.validate_turn` |
| Bench | Orchestrated workflow with a nested sub-workflow, baseline vs optimized, 3 reps | `tokenopt/evaluation/`, `evaluation/` |

### 3a. Integration point (review finding, 2026-10-10)
`tokenopt/handoff/` is NOT a `CanonicalOptimizer` pipeline stage. It is a pure function `compress_segment(text, kind) -> Result` applied once to each new tool result before the SDK appends it to history; the compressed text becomes the canonical history, so the prefix is stable by construction. It bypasses `execution.py` and the planner/transformer. On current `origin/main` (citations re-verified 2026-10-10 after rebase): the pipeline reprocesses the full history each call (`transformer.py:409`, `for idx, msg in enumerate(ctx.messages)`); a fatal validator violation triggers a full rollback that resets earlier messages (`validator.py:272-280`, rollback call at :276, partial revert at :280), which is not prefix-stable; the proxy flattens the whole conversation into one user message on every request, keeping only system messages separate (`tokenopt_proxy_v2.py:664-671`; `execution.py:101-103` builds the `role: content` prompt); and the executor's message normalization keeps only `role` and `content`, dropping `tool_calls`/`tool_call_id`/`name` (`execution.py:71-75`). Those are out of scope here but mean the proxy path is not a valid host for this design until fixed. A separate, unmerged fix for the normalization (commit 128b8ae, branch `fix/normalize-proxy-chat-messages`) adds `_normalize_message` but still keeps only role and content. Proxy use needs a content-hash memo to skip already-seen messages. `tokenopt_recall` is registered from turn 0 or not at all (tool bytes precede messages in the cached prefix). Contract impact: tool payloads are P0 in `architecture/context-preservation-contract.md` (`analyzer.py:43-44`, `397-406`); the handoff path needs an explicit carve-out (decision draft).

### 3b. Overlap with what main already ships (found at rebase, 2026-10-10)
- `tokenopt/pipeline/content_compressor.py` (`ContentCompressorStage`, default off, fail-open, between Analyzer and Transformer) already routes `role="tool"` and large assistant messages through headroom `compress()` with a pure-Python JSON array sampler fallback. This occupies the H2 (JSON/logs) slot and is a precedent for compressing tool payloads despite the P0 rule. It is a pipeline stage that reprocesses history, not an ingress-once function, so it does not by itself give prefix stability; whether it has a recall handle or protected-facts gate was not checked. Any H2 work should extend or replace this stage rather than add a second JSON compressor.
- `tokenopt/pipeline/cache_planner.py` (`CachePlannerStage`, lossless) already computes the byte-stable prefix across calls, flags cache-busting changes and estimates the cache discount (Anthropic 0.9, OpenAI 0.5). This overlaps the cache guard and the cache-discipline lever; the cache guard should reuse its prefix hashing instead of duplicating it. `docs/RUNTIME_STAGES_DESIGN.md` describes both.
- H1 (test/CI/build output) and H3 (diffs) are not covered by main. The census found no test/CI output worth more than 5-6% of weighted cost on bug-fix work and no diffs in the data.

## 4. Handler interface
```python
class Handler(Protocol):
    name: str
    def matches(self, seg: Segment) -> float: ...            # confidence 0..1
    def compress(self, seg: Segment, ctx: Ctx) -> Result: ...  # text, recall_handle|None, protected_ok, meta
```
Rules: deterministic; idempotent; never return more tokens than the input (else passthrough); any exception = passthrough and log; no network or model calls in v1.

## 5. Handlers, in build order
1. H1 test/build/CI output (pytest, jest, cargo, tsc, ruff, stack traces): keep failures, summary, exit status, first/last frames; collapse passes to counts; dedupe repeated lines with counts. Protected: failing test ids, error text, file:line.
2. H2 JSON and logs: drop nulls, empties, URL/avatar noise; ADF to text; homogeneous arrays keep schema, errors, outliers, first/last and counts; recall for the rest. Start from arm C in `experiments/handoff_phase1/arms.py` but note it only drops noise/empties, imports Jira-specific `adf_to_text` (line 16) and has no array summarisation or recall: those are new. Do not drop explicit `null` (e.g. null assignee means unassigned). Protected: keys, ids, numbers, statuses.
3. H3 diffs: keep hunks and changed lines, trim excess context. Protected: paths, changed lines.
4. H4 code outline (signatures only): only when the next step is orientation, not editing. Off by default until judged.
Ideas studied, not copied: rtk (per-command filters, recoverable output), Headroom (keep errors/outliers, reversible retrieval, cache alignment), Repomix (signature extraction). Check each license before reusing code; Apache-2.0 needs attribution.

## 6. Workflow layer (likely the largest end-to-end lever; hypothesis)
- Typed handoff contract per edge, for example `ImplementResult{summary, files_changed[], tests{passed, failed[]}, open_issues[], artifacts{path: handle}}`.
- Nested workflows return only their contract to the orchestrator.
- Each agent receives only the context its step needs; no transcript forwarding; no repeated re-reads (reference by handle).
- Terse structured outputs between agents; prose only in the final report.

## 7. Fidelity and safety gates
- Per handler: golden cases, protected-fact retention >= 99% (deterministic).
- Per workflow: end-to-end outcome >= 95% of baseline. Errors compound: 5 handoffs at 97% each is about 86% end to end (assumes independent errors).
- Fallback ladder per segment, every fallback logged. Lossy cuts must be recoverable or pass the judge.
- Tune on 70% of tasks, report on the held-out 30%. Report misses.

## 8. Benchmark
Subject repo: TokenOpt. Orchestrator -> [implement workflow -> test workflow] -> review, on 20 tasks (fix failing test, add tests, refactor, review a diff, triage CI failure). Baseline vs optimized, 3 reps. Report tokens, weighted cost (cached/uncached/output, stated prices), success rate, extra turns, per-category and per-agent attribution. External baselines: rtk, Headroom, Repomix compress.

## 9. Build order and checkpoints
0 branch `feat/workflow-optimizer` -> 1 ledger and trace extension -> 2 H1 + tests -> 3 H2 + tests -> 4 recall store + cache guard -> 5 handoff contracts in the demo workflow -> 6 end-to-end baseline run (needs spend approval) -> 7 optimized run, compare -> 8 H3/H4 only if the census justifies -> 9 report and demo.
Stops: design approval, spend approval, first end-to-end result, before any commit or push.

## 10. Non-goals
No LiteLLM. No ML models in v1 (LLMLingua, LongCodeZip as baselines only). No key aliasing (rejected in TCC research). No history rewriting. No proxy persistence stack (Postgres, Redis, Kafka) in the demo path.

## 11. Risks
- The workload mix may be prose-heavy, in which case 30-40% is not reachable; the report must say so.
- Handlers over-compress a needed detail; mitigated by protected facts, recall handles and the fallback ladder.
- Induced extra turns erase savings; counted in the metric.
- Failure modes (review): (1) cache-prefix break from nondeterminism (dict order, timestamps), rollback flips or late tool registration; (2) silent over-compression compounding across edges (record per-edge outcome in the ledger); (3) recall abuse: re-inflation, path traversal, sensitive storage; (4) extra turns/re-reads erase savings (handler fails its gate if held-out turn delta > 0); (5) non-idempotent handlers or misrouting (test `h(h(x)) == h(x)`, marker prefix on compressed segments, low confidence = passthrough).
- Licenses: rtk and headroom Apache-2.0 (verified LICENSE), repomix MIT (likely). Code reuse needs attribution/NOTICE; NOTICE files and dependencies not checked. Headroom CacheAligner behavior unverified; read its README before relying on it.
- Scope creep: four handlers maximum for the demo; a handler ships only if it passes its gate.

## 12. Approvals needed from the user
1. New package `tokenopt/handoff/` and new config flags (architecture and API decision; draft the `.ai/DECISIONS.md` entry, do not write it).
2. Spend approval for the paid benchmark runs.
3. Whether to commit and push at each milestone.
