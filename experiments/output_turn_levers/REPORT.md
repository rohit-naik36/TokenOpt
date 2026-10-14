# otl-001 Stage 1 report (local qwen3.5:9b via Claude Code 2.1.286, task T1, 20 runs per arm)

Status: **IMPLEMENTED and VERIFIED against the run artifacts** (80 run dirs, 604 model turns; the census CLI on the same dirs reports 80 sessions, 604 turns, and per-run sums match). Run directories live in the Aegis worktree `docs/evidence/ctxopt-v1/otl-001/runs/` (untracked there, 18 MB) and were not copied here. Analysis: `analyze.py`; numbers: `results.md` / `results.json`; pooled census: `census_pooled.json`.

## Procedure and deviations
- Judge deviation recorded before scoring: Amendment 2 in `docs/EXPERIMENT_OUTPUT_TURN_LEVERS.md` (commit a3b689a): judge is Claude Code (Sonnet 5.5), temperature uncontrollable, not the planned API judge; hidden-test pass rate is primary, judge score secondary.
- Judging: diffs only (the rubric scores the diff), under random IDs (`blind/`), scored against `otl_rubric.md` with fixed rules: tests 3 = normal + separator runs + leading/trailing + empty-or-symbol-only input, 2 = one missing; correctness judged on the code; minimality/hygiene docked only for clear unrelated edits or misleading leftovers. Scores (`scores.csv`) were committed before `id_to_arm.json` existed in the repo or was read into the analysis.
- Blinding was imperfect: the judging session had already seen `progress.jsonl` (per-run arm, success, turns, tokens) and knew one C run failed. It had not seen any judge score.
- `progress.jsonl` had duplicate re-logged lines (identical except `ts`); 80 unique run_ids, no stray containers.

## Results (means, percentile-bootstrap 95% CI, 10,000 resamples, seed 20261014)
See `results.md` for the full tables (including output-weight 1 and 8 sensitivity and Holm-adjusted p).

| arm | pass | judge /10 | output tokens | turns | tokens/turn | W |
|---|---|---|---|---|---|---|
| control | 20/20 | 9.95 | 2284 | 7.70 | 5748 | 19348 |
| A | 20/20 | 9.90 | 1410 | 7.35 | 5314 | 14966 |
| B | 20/20 | 9.80 | 2064 | 8.55 | 5751 | 19075 |
| C | 19/20 | 9.35 | 1135 | 6.60 | 5175 | 13013 |

Ratio to concurrent control: output tokens A 0.62 [0.49, 0.77], B 0.90 [0.76, 1.08], C 0.50 [0.42, 0.58]. Turns A 0.95 [0.79, 1.14], B 1.11 [0.95, 1.29], C 0.86 [0.72, 1.01]. Tokens per turn A 0.92 [0.87, 0.98], B 1.00 [0.95, 1.05], C 0.90 [0.86, 0.94]. Weighted cost W (secondary) A 0.77 [0.65, 0.92], B 0.99 [0.85, 1.14], C 0.67 [0.59, 0.77]; at output weight 1: A 0.86 [0.73, 1.00], C 0.77 [0.68, 0.88].

## Quality gate (arm >= 95% of control)
- Pass rate (primary): A 1.00, B 1.00 PASS; C 0.95 PASS **exactly at the boundary** (19/20 vs 20/20; Wilson 0.76-0.99).
- Judge score (secondary): A 0.995, B 0.985 PASS; **C 0.940 FAIL**. The shortfall comes from one run, C rep 5 (the only hidden-test failure: kept non-ASCII letters via `\w`; blind score 6/10, the blind judge flagged the spec deviation independently). Post-hoc, not pre-registered: excluding that run C's judge mean is 9.50 (0.955). The two gate criteria disagree for C and are not merged (Amendment 2).

## What the data support
- A and C: output tokens fall (CI excludes 1), and W falls; B shows nothing. Turn count: no arm's CI excludes 1 (C's upper bound is 1.01), so turn discipline (B) did not reduce turns here and made them nominally higher.
- C's token saving comes with a quality signal that is not clean (one genuine task failure; judge gate fails). One failure in 20 cannot separate a real quality cost from chance.

## Limitations
- Stage 1 only: qwen3.5:9b through Claude Code on one task (T1). Does not transfer to Claude models or other tasks (Amendment 1 item 8).
- n = 20 per arm; no placebo arm of matched length; B's batching had little room (about one tool call per turn).
- Judge is the same model family as the project's other tooling, non-deterministic, with a rubric where most runs saturate at 9-10 (low resolution). Test-coverage scores follow my own fixed rule, not an independent one.
- Judge scores are a single pass; no second judge or re-judge was run to measure agreement.
- Multiplicity: Holm is applied across the 3 primaries within each arm, not across arms.
