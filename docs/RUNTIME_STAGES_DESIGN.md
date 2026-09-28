# Design: runtime savings stages (CachePlanner, ObservationElision)

> **Status: DESIGN ONLY — no code.** Draft for review. Motivated by measured
> trajectory results: the deterministic optimizer saves ~1.8% on real agent
> context, while the repeated prefix is ~42% of input (cache-eligible) and
> stale observations ~24% (lossy upper bound). These two stages target those
> levers instead of prose compression.

Both stages are `PipelineStage`s composed into the canonical pipeline. Neither
rewrites content the way the Transformer does; they operate on message
*structure* and *metadata*. Both are **off by default** and opt-in via config.

---

## A. CachePlannerStage

**Goal:** maximize provider prompt-cache hits by keeping the stable prefix
byte-identical across calls and marking where the cache boundary should sit.
Lossless — it never changes token content, only annotates and guards.

**Placement:** first stage, before the Analyzer (it must see the raw, unmodified
messages; any later stage that rewrites the prefix would defeat caching, so the
planner also records the pre-transform prefix hash for the busting check).

**Responsibilities**
1. **Identify the stable prefix.** Walk messages from the front while each is
   byte-identical to the previous call's message at the same position (system,
   tool schemas, demonstrations, long fixed instructions). Requires a per-session
   memory of the previous call's prefix hashes (keyed by a caller-supplied
   session id; falls back to within-request structural heuristics when absent).
2. **Insert cache breakpoints (Anthropic).** Attach `cache_control: {type:
   "ephemeral"}` to the last content block of the stable prefix (and at most the
   4 breakpoints Anthropic allows), choosing boundaries at the largest stable
   spans. Emitted as message metadata the provider adapter serializes.
3. **Flag cache-busting content.** Detect prefix bytes that change call-to-call
   (a timestamp, a per-request id, a reordered tool list) and report them, since
   one changed prefix byte invalidates the whole cached prefix.
4. **Report expected cache-hit rate.** From the stable-prefix token count vs
   total input, emit `cache_eligible_tokens`, `cache_eligible_pct`, and the
   per-call expected discount given a configured provider discount factor.

**Config** (all optional): `enable_cache_planner=False`, `session_id`,
`max_breakpoints=4`, `min_prefix_tokens` (skip trivially small prefixes),
`provider_discount` (for reporting only).

**Metrics:** `cache_eligible_tokens`, `cache_eligible_pct`, `cache_breakpoints`,
`cache_busting_spans`, `expected_cache_saved_tokens`.

**OpenAI note:** OpenAI prompt caching is **automatic** for prompts ≥1024 tokens
with a stable prefix — there is **no `cache_control` to insert**. On OpenAI the
stage is largely redundant: breakpoint insertion is a no-op, and only the
**prefix-stability guard and cache-busting detection** remain useful (they help
the automatic cache actually hit). The stage should detect the provider and skip
breakpoint emission for non-Anthropic targets.

**Risks / non-goals:** does not itself reduce tokens (savings come from the
provider); depends on prefix stability, so it must run before, and constrain,
any content-rewriting stage; cross-call session memory is new state to manage.

---

## B. ObservationElisionStage

**Goal:** bound long agent contexts by replacing old tool observations with a
one-line placeholder, keeping the last N verbatim. Lossy — off by default and
policy-gated.

**Placement:** after the Analyzer (so tool/observation messages are already
classified), before the Validator (so elision is validated like any change).
Elision is a structural edit, not a content rewrite.

**Responsibilities**
1. **Identify tool observations.** Use the preservation map / roles to select
   messages that are tool outputs (environment observations), excluding the
   system prompt, demonstrations, the current user turn, and the stable prefix.
2. **Keep the last N.** Retain the most recent `keep_last` observations verbatim.
3. **Elide older ones.** Replace each older observation's content with a compact,
   deterministic placeholder that preserves a recall handle, e.g.
   `[observation from turn K elided — N tokens]`, optionally with a first-line
   summary. Never elide a message carrying a preserved invariant unless policy
   explicitly allows it.
4. **Report.** Emit elided count and tokens saved.

**Config:** `enable_observation_elision=False` (default off), `keep_last=5`,
`summary_mode` (`placeholder` | `first_line`), `protect_invariants=True`.

**Metrics:** `observations_total`, `observations_elided`, `elision_tokens_saved`.

**Interaction with caching:** elision must **not** touch the stable prefix (that
would bust the cache); it only rewrites the variable middle of the context, so it
composes cleanly with CachePlannerStage.

**Risks / non-goals:** lossy — eliding an observation the agent still needs can
change task outcome, so it must be validated against task-success replay before
default-on for anyone; it is a heuristic stand-in for a proper recall store
(retrieving elided content on demand), which is a larger follow-up.

---

## Pipeline composition (proposed, all opt-in)

```
CachePlanner → Analyzer → [ContentCompressorStage?] → ObservationElision → Transformer → Validator
```

`ContentCompressorStage` (an opt-in headroom-backed tool-output compressor) does
not exist in the codebase yet and is out of scope for this design; the bracket
marks where such a stage would sit if built. The legacy BPE `CompressorStage` is
**not** used — its truncation is the lossy path CP7 removed.

The Validator's per-message revert (already shipped) is the safety net for the
lossy/edit stages: any message an edit stage damages is reverted individually
without discarding the rest. Rollout order: CachePlanner first (lossless, biggest
lever), ObservationElision only behind a measured task-success gate.
