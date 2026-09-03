# Workflow: Performance Investigation

_Owner: `.ai/ROLES/backend-engineer.md`, verdict reviewed by `.ai/ROLES/architect.md`_
_Standards: testing, coding, git; related: `.ai/DOD.md`_

## Purpose

Investigate a latency, throughput, or cost concern with evidence — never
optimize on vibes. TokenOpt's own metrics (latency split, token counts,
cost estimates) are the primary measurement surface.

## Prerequisites

- A symptom: user report, metric anomaly, UAT finding, or release
  regression.
- A measurable baseline (or a defined way to capture one).

## Steps

1. **Measure first** — capture the baseline using recorded metrics
   (`latency_ms` = `model_latency_ms` + `pipeline_latency_ms`) or a
   reproduction script; record numbers in the session.
2. **Localize** — split the cost: model inference vs TokenOpt pipeline
   stages (`{stage}_latency_ms` metrics); token counts and cost estimates
   for cost issues. Find the stage or call that dominates.
3. **Hypothesis** — one hypothesis, one change; prefer measurement tools
   (metrics, profiling) over guessing.
4. **Change** — smallest change per coding-standard; behavior must stay
   identical (fail-open preserved); no public API changes without approval.
5. **Re-measure** — same measurement as step 1; report before/after;
   reject the change if it does not move the number.
6. **Verify + commit** — full gates (Verification); `perf:` or `fix:`
   commit (git-standard); push (Decision 11).
7. **Record** — findings in SESSION_LOG; tuning notes (thresholds,
   trade-offs) in the relevant docs if user-visible (README config table).

## Verification

```bash
pytest tests/ -q
ruff check tokenopt tests
mypy tokenopt
```

## Expected outputs

- Evidence-based diagnosis (numbers, not opinions)
- Optimized change with measured improvement
- Trade-off documented (e.g. accuracy vs speed) when relevant

## Completion criteria

- [ ] Baseline and post-change numbers recorded
- [ ] Change moved the measured number (or was rejected)
- [ ] Gates green, behavior unchanged
- [ ] Committed + pushed
