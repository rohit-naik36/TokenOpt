# Routing Precedence Review — pre-M13 architecture decision

_Date: 2026-08-01_
_Reviewer: `.ai/ROLES/architect.md` (architecture-review workflow); user is
the approval gate for routing behavior (Decision 24)._

## 1. Problem statement

When custom routing rules are configured but none match, the complexity
fallback rewrites the requested model to `gpt-4o` / `gpt-4o-mini`:

- On **OpenAI** this silently overrides the caller's model choice.
- On **Anthropic / LocalClient** (where only provider-relevant rules are
  kept, Decisions 8 + 13) the complexity fallback can rewrite the model
  to a `gpt-*` model, which is invalid for that backend and **breaks the
  API call** — violating fail-open (Decision 21).

## 2. Current implementation (before)

`tokenopt/pipeline/router.py::RouterStage.process`:

1. No user query → `ctx.model = config.default_model` (overwrites even an
   explicitly requested model).
2. Rules (all `routing_rules`, any provenance) checked in priority order;
   first match wins → `ctx.model = rule.model`, `routing_rule` +
   `routed_model` recorded.
3. No match → complexity heuristic (keyword + token count) → rewrites
   `ctx.model` to `gpt-4o`/`gpt-4o-mini`, records `routing_complexity`.

`routing_reason` (Decisions 19–20) = matched rule name, else
`complexity-based (low|medium|high)`, else empty. There is no record of
the precedence decision itself.

## 3. Proposed precedence (user-approved objective)

1. **Explicit caller model** (highest) — caller passed `model=` to the
   client: never overridden.
2. **Matching routing rule** — first match by priority.
3. **Custom rules exist but none match** — preserve the caller's
   requested model.
4. **No custom routing configuration** — built-in complexity routing.
5. **Provider default** (last resort) — nothing routed; resolved model
   stands.

## 4. Review findings

### F1. Provenance of rules matters
`get_default_config()` ships built-in rules (simple/code/reasoning) in the
same `routing_rules` field as user-supplied rules. Precedence 3 vs 4
differ only by whether rules are **custom** (user-supplied). Without
provenance, precedence 3 would also capture built-in defaults and change
default-config behavior (unmatched queries would stop getting complexity
routing) — a silent behavior change for users who configured nothing.

**Resolution:** mark built-in rules with `RoutingRule.builtin=True` in
`get_default_config()`. Precedence 3 applies when any non-builtin rule
exists; precedence 4 when none does. Default-config users see **zero
behavior change**; the fix targets only custom-rule configurations (the
reported bug).

### F2. Explicit-model detection
`chat_completion` resolves `model = model or default_model` before the
pipeline runs, so the router cannot tell "caller asked for gpt-4o" from
"default filled in". Precedence 1 needs explicitness as first-class data.

**Resolution:** `OptimizationContext.model_explicit` (additive field),
plumbed from `chat_completion` (`model is not None`) through
`OptimizationPipeline.run`. `LocalClient.chat_completion` computes
explicitness before resolving its local default. Fully backward
compatible: new optional parameter `model_explicit=None` on
`chat_completion` (derive when None).

### F3. Provider-client impact (Anthropic / LocalClient)
Both already filter rules per provider (Decisions 8 + 13) and build a
router only when provider-relevant custom rules exist. Under the new
precedence, a no-match with custom rules **preserves the caller's model**
instead of falling into complexity → eliminates the `gpt-*` rewrite on
Claude/local calls. The provider filters themselves are unchanged.

### F4. Empty-query path
Old code overwrote `ctx.model` with `config.default_model` even for an
explicit caller model. New precedence: explicit → precedence 1
(preserved); implicit with no query → precedence 5 (resolved model
stands — identical outcome in the real flow, since the resolved model
already is the default).

### F5. Fail-open compatibility
Complexity rerouting on no-match is itself an optimization decision, not
a failure — but it can turn a valid caller model into an invalid backend
model. Preserving the caller's model is the most fail-open-compatible
choice (never breaks the request, per Decision 21).

### F6. `routing_reason` completeness (Decision 20 extension)
Decision 20's mapping (rule name / `complexity-based (X)` / empty) cannot
express "rules evaluated but none matched". Requirement: routing_reason
must reflect the final decision. Add `preserved (no rule matched)` for
precedence 3; add machine-readable `RequestMetrics.routing_precedence`
(`explicit | rule | preserve | complexity | provider_default`) alongside.

## 5. Compatibility impact

| Change | Type | Compatible |
|--------|------|-----------|
| `RoutingRule.builtin` (default False) | public API, additive | ✅ |
| `RequestMetrics.routing_precedence` (default "") | public API, additive | ✅ |
| `OptimizationContext.model_explicit` | internal, additive | ✅ |
| `chat_completion(model_explicit=None)` | public API, additive keyword | ✅ |
| Behavior: explicit model never overridden by rules | behavior | **Intentional change** — precedence 1 |
| Behavior: custom rules, no match → preserve (was: complexity rewrite) | behavior | **Intentional change** — the fix |
| Behavior: default config, no match → complexity (unchanged) | behavior | ✅ unchanged |
| Behavior: empty query → resolved model stands | behavior | ✅ equivalent in real flow |

Drop-in contract: existing callers never pass `model_explicit`; callers
that explicitly pass `model=` and previously relied on routing rules
overriding them now get their model honored (the point of the decision).
Callers who pass no `model` are unaffected.

## 6. Final recommendation

**Approve and implement the five-level precedence** with the provenance
refinement (F1): built-in default rules keep complexity fallback for
default-config users; custom rules never trigger a complexity rewrite on
no-match — the caller's requested model is preserved; an explicitly
passed model is never overridden. Record as Decision 24; implement now
(pre-M13); M13 refactor proceeds afterward.

## 7. Evidence

- Tests: `tests/test_router.py` (contract), `tests/integration/test_metrics_clarity.py`,
  `tests/integration/test_anthropic_flow.py` (new + updated cases).
- Verification: `pytest tests/` 158+ green, `ruff`, `mypy`, examples
  validated against the stub server, CI green.
