# Experiment: output-discipline and turn-discipline levers (pre-registration)

Status: **PRE-REGISTRATION, written before any run.** Frozen at the commit that adds this file. Deviations after the first run are recorded in a `Deviations` section of the report, never edited in here. Date: 2026-10-11. Branch: `feat/output-turn-levers`.

## 1. Question
The Phase 1b census (`experiments/sdlc_census/REPORT.md`) found that on the Aegis T1 bug-fix task, context-compression levers cap near 10% of weighted cost even at 100% removal, while output is 44-45% of weighted cost and one average turn is 12-15%. Can instruction-level changes to agent behaviour reduce output tokens and turn count, and therefore weighted cost, without losing task quality?

This is a test of a hypothesis, not a claim. A null or negative result is reported as is.

## 2. Evidence this builds on (all OBSERVED, from the census)
| quantity | value | source |
|---|---|---|
| Aegis control sessions (T1, qwen3.5:9b via Claude Code) | 30 in the census (baseline_variance, t1a, t1b) | `experiments/sdlc_census/results/census.json` |
| Mean per session | 9 turns, 55,916 prompt tokens (48,951 cached), 2,393 output tokens | same |
| Weighted cost W per session | mean 21,432; **CV 0.50** | same |
| Output share of weighted cost | 44-45% (about half is tool-call arguments, i.e. the work product) | census |
| One average turn | 12-15% of session cost | census |
| Success of control runs | 48 of 50 control run directories report success | `experiments/cost_model/results/*/runs/*control*/result.json` |

## 3. Arms (one change per arm)
All arms use the same harness, task, model, flags and system prompt. The only difference is one instruction block, delivered via `--append-system-prompt` so its bytes are identical on every turn (prefix-stable). The control arm gets nothing appended. Instruction texts are frozen here.

- **CONTROL**: no appended text.
- **A, output discipline**: "Be terse. Do not restate file contents, the task, or your plan. Make edits as the smallest possible diffs (smallest old_string/new_string); never rewrite a whole file. After finishing, reply with one line."
- **B, turn discipline**: "Before your first tool call, write a plan of at most 3 lines, once. Batch independent tool calls into a single turn (for example read every file you need together). Stop as soon as the visible tests pass. You have a budget of 8 tool-using turns." (8 is the control median turn count in the census; frozen now, not tuned afterwards except as in section 6.)
- **C = A + B**: the A text followed by the B text.

Limitations of this design, stated in advance: the appended text itself adds prefix tokens (cached after the first turn); there is no length-matched placebo arm; T1 averaged about 1.0 tool calls per turn in earlier runs, so batching (arm B) may have little room on this task.

## 4. Workload and baseline
- **Task**: Aegis `ctxopt_v1` **T1** ("small-context": add `slugify` to `textutils.py`), hidden tests in the offline evaluator container. T2 and T3 are excluded because both earlier controls exhausted the 900 s cap (n=1 each).
- **Substrate (Stage 1)**: unchanged `ctxopt_v1.2` harness, Claude Code 2.1.286, `qwen3.5:9b` via the relay to Ollama, `--budget-s 900`, model unloaded before every run (cold cache), as in `experiments/cost_model/BASELINE_VARIANCE_PREREGISTRATION.md`.
- **Existing control sessions** (30 in the census, taken over several days) are the historical reference only. They fix the expected scale and variance (CV 0.50) and the success rate. They are **not** the comparison group, because the arms and the controls must share the same day, the same Ollama state and the same ordering.
- **Fresh controls needed for comparability: the same number as each arm** (20 per arm recommended, 10 minimum). Runs are interleaved rep-major (control, A, B, C for rep 1, then rep 2, and so on) so drift hits all arms equally.
- **Harness change required (outside this repo)**: the Aegis harness currently implements only the `control` condition and refuses any other (`contract.py` `CONDITIONS`). Arms need new conditions that pass `--append-system-prompt`. This changes the contract digest and the harness version, and needs the user's explicit authorization for Stage 2 of that harness. No change has been made.

## 5. Metrics
- **Primary**: weighted cost per run `W = uncached_prompt + 0.1 * cached_prompt + 4 * output_tokens`. Prices are ASSUMED relative weights (uncached 1, cached 0.1, output 4), with sensitivity at output weight 1 and 8.
- **Secondary**: turns, tool calls, output tokens, total tokens, duration, success (hidden AND visible tests pass and agent exit 0 and not timed out), and the judge score.
- **Share table and measured effect per arm**: `python -m tokenopt.census <new run dirs>` (it reads Aegis run directories), plus the analysis script written for this experiment.
- Failures (`workspace_incorrect`, `budget_exhausted`, `agent_error`) are data and stay in the all-runs statistics. A `harness_error` is excluded, counted, and replaced (at most 2 replacements; a third stops the experiment).

## 6. Success criteria (fixed now)
1. **Quality gate**: for each arm, (a) test pass rate >= 95% of the control's pass rate, and (b) the temperature-0 LLM judge's mean patch score >= 95% of the control's. Wilson intervals are reported. With 20 runs per arm the gate cannot statistically rule out a drop of 20-30 percentage points, so a pass means "not distinguishable at this n", not "equivalent".
2. **Judge**: blind to arm, temperature 0, written rubric (correctness against the spec, minimality, no invented APIs, tests added), run on the final workspace diff. Planned model: `claude-sonnet-4-6` at temperature 0, because the current Claude 5-family models reject non-default sampling parameters. Rubric text is committed before the first judging call.
3. **Replication**: at least 10 reps per arm, 20 recommended.
4. **Effect**: cost and token reduction versus the concurrent control with 95% confidence intervals (percentile bootstrap, 10,000 resamples, fixed seed, on log W so the ratio of geometric means is reported; Mann-Whitney as a secondary check).
5. **Tune / hold out**: reps are assigned by index before running: the first 70% of reps per arm are the tuning set (14 of 20), the last 30% the held-out set (6 of 20). Allowed tuning is limited to choosing between at most two pre-written wordings per arm and the turn-budget number, using tuning reps only. The choice is then frozen and the held-out reps are run. **The headline is the held-out result.** The all-runs result is reported as secondary and labelled contaminated by tuning.
6. **Decision labels**: "promising, replicate" requires a held-out weighted-cost reduction with a 95% CI excluding zero AND the quality gate passed. Anything else is "not shown". A result whose CI includes zero is "inconclusive", not "no effect". A cost increase or quality loss is reported as a negative result.

## 7. Power (CV of W from the census is 0.50, so this matters)
Minimum detectable relative difference at alpha 0.05 (two-sided), power 0.8, normal approximation, CV 0.50:

| runs per arm | minimum detectable difference |
|---|---|
| 10 | about 63% |
| 20 | about 44% |
| 30 | about 36% |
| 40 | about 31% |

Detecting a 25% reduction needs about 63 runs per arm, and a 15% reduction about 175. The held-out subset (6 per arm) is far below this. **Consequence: with the planned sample, only a very large effect can be detected, and a CI that includes zero is the likely outcome. This experiment can find a large effect or exclude nothing.** Reducing the variance (for example, analysing conditional on success, or using output tokens as the endpoint) does not change that arithmetic much because output tokens also have CV about 0.50. If a larger effect is not seen, the honest next step is either more runs or a different task, not a claim.

## 8. Cost estimate
Prices (USD per million tokens, from the model list as of 2026-10-06; cache reads at the listed rates): Haiku 5.5 $0.10 in / $0.50 out (cache read ASSUMED $0.01); **Sonnet 5.5 $2.00 / $10.00, cache read $0.20**; **Opus 5.5 $4.00 / $20.00, cache read $0.20**; judge `claude-sonnet-4-6` $3.00 / $15.00. Per-run token profile is the census mean (55,916 prompt of which 48,951 cached, 2,393 output, 9 turns). A stronger model may use fewer or more turns than the 9B model; that is an assumption, not a measurement.
- Low case: prompt caching works as in the census, output unchanged, cache writes at 1.25x on one turn's worth of the cached prefix.
- High case: no caching, output tokens 3x (thinking).

**Stage 1 (recommended): same substrate as the existing controls, local qwen3.5:9b, API cost $0.**
| item | runs | API cost | local time |
|---|---|---|---|
| 4 arms x 10 reps | 40 | $0 | about 4 h at about 6 min per run incl. model unload |
| 4 arms x 20 reps | 80 | $0 | about 8 h |
| judge, 80 patches (3,000 in / 300 out each, Sonnet 4.6) | 80 | about $1.08 (40 patches: $0.54) | none |

**Stage 2 (optional, only after Stage 1 shows a signal, or if a paid-model claim is wanted): a paid agent model.** This needs the relay pointed at the Anthropic API (a harness change) and fresh controls on the same model, because the 30 existing controls are qwen3.5:9b and are not comparable.
| agent model | per run (low - high) | 80 runs (4 arms x 20) | 40 runs |
|---|---|---|---|
| claude-haiku-5-5 | $0.003 - $0.009 | $0.2 - $0.7 | $0.1 - $0.4 |
| claude-sonnet-5-5 | $0.05 - $0.18 | $4.0 - $14.7 | $2.0 - $7.3 |
| claude-opus-5-5 | $0.09 - $0.37 | $7.3 - $29.4 | $3.6 - $14.7 |
Add the judge (about $1.08) to each. A 2x contingency for failed or repeated runs gives a ceiling of about $62 for Opus 5.5 at 80 runs; Sonnet 5.5 about $32.

## 9. Checkpoint: needs the user's approval before any model call
1. Spend approval: Stage 1 (about $1.08 judge only) and, separately, whether Stage 2 is wanted and its ceiling.
2. API key: `ANTHROPIC_API_KEY` set in the environment by the user (needed for the judge in Stage 1, and for the agent in Stage 2). It is never written to a file or committed.
3. Authorization to add the arm conditions to the Aegis harness (external repository; the contract currently refuses non-control conditions).
4. GPU availability for roughly 4-8 hours of Stage 1, including model unload/reload between runs.
No paid model is called before these are given.

## 10. After approval
Run the interleaved matrix, copy each run directory unmodified under `experiments/output_turn_levers/results/`, run `python -m tokenopt.census` on the new directories for the share table, then report per arm: effect with CI, quality gate result, held-out headline, and what did not work.
