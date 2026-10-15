# Stage 2 results: n8n SDLC workflow on claude-haiku-5-5 (phase A, no caching)

**Status: phase A only (no caching). The blind quality judge has not been run. Section 7a is a post-hoc diagnosis added after the main results; it changes no gate or threshold.**

Pre-registered in `STAGE2_PREREGISTRATION.md` (sections 1-17). Scoring deviations are in section 17 and were committed before results were computed. Thresholds, decision labels and the gate are as written in sections 6 and 10. No threshold was changed after seeing results.

Data: 8 tickets x 4 arms x 5 reps = 160 runs, 800 stage calls, all `end_turn`, zero `max_tokens`, zero errors, zero retries. Cost $0.364969 (logged $0.365). Scoring: `stage2_score.py` (imports the Stage 1 checks from `score.py`, unchanged). Tables: `stage2_analysis.py`. Per-run scores: `full_s2_scored.jsonl`.

Method check: `stage2_score.py --check-stage1` reproduces all nine published Stage 1 ratio intervals (W, output tokens and total tokens for A, H and AH) from `scored.jsonl`, so the bootstrap used here is the Stage 1 method.

## 1. Token and cost totals (usage fields, phase A, no cache terms)

| arm | runs | input (uncached) | output | total | mean $/run | total $ |
|---|---|---|---|---|---|---|
| control | 40 | 459,801 | 139,981 | 599,782 | 0.00290 | 0.115971 |
| A | 40 | 408,733 | 104,020 | 512,753 | 0.00232 | 0.092883 |
| H | 40 | 197,768 | 133,758 | 331,526 | 0.00217 | 0.086656 |
| AH | 40 | 200,128 | 98,892 | 299,020 | 0.00174 | 0.069459 |
| **all** | 160 | 1,266,430 | 476,651 | 1,743,081 | | **0.364969** |

Cache write and cache read are zero in every call, so W = input + 4 x output here.

## 2. Ratio versus control, with 95% ticket-cluster CIs

Ratio of sums over paired (ticket, rep) units; 8 ticket clusters; 10,000 resamples; seed 20261015. Reading uses the section 10 rules. Stage 1 columns are the same method on the local model.

| arm | endpoint | Stage 2 ratio [95% CI] | Stage 2 reading | Stage 1 ratio [95% CI] | Stage 1 reading |
|---|---|---|---|---|---|
| A | W | **0.81** [0.79, 0.82] | reduction | 0.90 [0.86, 0.93] | reduction |
| A | total tokens | 0.85 [0.84, 0.87] | reduction | 0.94 [0.91, 0.96] | reduction |
| A | output tokens | 0.74 [0.72, 0.76] | reduction | 0.82 [0.77, 0.87] | reduction |
| A | dollars | 0.80 [0.79, 0.81] | reduction | n/a | n/a |
| H | W | **0.72** [0.70, 0.74] | reduction | 0.71 [0.66, 0.75] | reduction |
| H | total tokens | 0.55 [0.54, 0.56] | reduction | 0.60 [0.57, 0.62] | reduction |
| H | output tokens | 0.96 [0.93, 0.98] | reduction | 0.90 [0.81, 0.98] | reduction |
| H | dollars | 0.75 [0.73, 0.77] | reduction | n/a | n/a |
| AH | W | **0.58** [0.57, 0.60] | reduction | 0.67 [0.64, 0.69] | reduction |
| AH | total tokens | 0.50 [0.49, 0.51] | reduction | 0.59 [0.58, 0.61] | reduction |
| AH | output tokens | 0.71 [0.68, 0.73] | reduction | 0.79 [0.74, 0.84] | reduction |
| AH | dollars | 0.60 [0.58, 0.62] | reduction | n/a | n/a |

Sensitivity for W (output weight 1 / 8): A 0.85 / 0.79; H 0.55 / 0.80; AH 0.50 / 0.63.

Every endpoint for every arm has a CI entirely below 1, so all are labelled reductions. These CIs are indicative only: with 8 clusters the percentile interval is coarse and probably too narrow (as Stage 1 Amendment 2 already notes). The Stage 2 intervals are narrower than Stage 1's; I did not test why.

## 3. Quality gate (pre-registered rule, section 10)

Format rate = every stage parses, has the required keys and ranges, and is not truncated. Control's format rate is 0.30, below 0.5, so the format component is **declared uninformative** under section 10 and the gate uses defect-hit only. Format rates are still reported.

| arm | format (all 5 stages ok) | defect-hit | format gate | defect-hit gate (>= 95% of control) | composite pass (Wilson 95%) |
|---|---|---|---|---|---|
| control | 12/40 (0.30) | 25/40 (0.62) | reference | reference | 12/40 (0.18-0.45) |
| A | 19/40 (0.47) | 32/40 (0.80) | n/a | **PASS** (0.80 vs 0.62) | 19/40 (0.33-0.63) |
| H | 5/40 (0.12) | 20/40 (0.50) | n/a | **FAIL** (0.50 vs 0.62; threshold 0.59) | 5/40 (0.05-0.26) |
| AH | 14/40 (0.35) | 27/40 (0.68) | n/a | **PASS** (0.68 vs 0.62) | 14/40 (0.22-0.50) |

Failure reasons, all arms: review stage 56 not-JSON and 53 `summary` key missing or misnamed (44 with no `summary` key, 9 with `" summary"`); release_note 4 `changes` out of range, 2 not-JSON, 2 summary over 60 words; plan 1 not-JSON; requirements 2 missing list keys.

Note the composite pass rates are reported for completeness and are not the gate. The composite pass rate for the repaired-brace variant equals the strict rate in every arm, because no Stage 2 output needed brace repair.

## 4. Stage 1 (qwen3.5:9b, local) and Stage 2 (Haiku 5.5) side by side

| arm | Stage 1 format | Stage 1 defect-hit | Stage 1 gate | Stage 2 format | Stage 2 defect-hit | Stage 2 gate |
|---|---|---|---|---|---|---|
| control | 0.07 | 0.65 | reference | 0.30 | 0.62 | reference |
| A | 0.10 | 0.62 | defect PASS (format n/a) | 0.47 | 0.80 | defect PASS (format n/a) |
| H | 0.28 | 0.72 | defect PASS (format n/a) | 0.12 | 0.50 | defect **FAIL** |
| AH | 0.28 | 0.60 | defect **FAIL** (format n/a) | 0.35 | 0.68 | defect PASS (format n/a) |

Transfer rule (section 10: same direction on W with the CI excluding 1, and the Stage 2 gate passing):
- **A: transferred.** W reduction in both stages; Stage 2 gate passes.
- **H: not transferred.** W reduction in both stages, but the Stage 2 defect-hit gate fails.
- **AH: cost transfers; quality transfer is not established.** Under the rule as written AH counts as transferred (W reduction in both stages, Stage 2 gate passes). The Stage 1 gate for AH failed (0.60 vs 0.65), so the Stage 2 pass does not reproduce the Stage 1 quality result, and both gates are dominated by JSON formatting (section 7a).

Cost decisions (section 8): A and AH are promising, since their cost reductions come with a passing gate. H's W reduction is a quality-cost trade-off, because its gate fails.

## 5. Per-stage mean tokens per run (prompt / output)

| arm | triage | requirements | plan | review | release_note |
|---|---|---|---|---|---|
| control | 939 / 195 | 1058 / 720 | 1787 / 1364 | 3657 / 921 | 4054 / 299 |
| A | 1009 / 176 | 1109 / 586 | 1702 / 911 | 3120 / 682 | 3278 / 246 |
| H | 809 / 190 | 668 / 701 | 938 / 1319 | 2010 / 931 | 519 / 202 |
| AH | 879 / 170 | 738 / 547 | 939 / 900 | 1862 / 679 | 585 / 177 |

## 6. Blind judge (secondary; packets exported, **judge not run**)

160 blind packets are in `blind_s2/` (same format as Stage 1, with no arm, run id or rep). The id-to-run map is `blind_map_s2.json`. It was written at export and has not been opened. It is not committed, so that no judge session can read it from git history. No judge scores exist for Stage 2, so no judge result is reported.

## 7. Finding that bears on the defect-hit gate

Every parseable review contains the planted defect: 25/25 (control), 32/32 (A), 20/20 (H), 27/27 (AH). Every miss is a review that is not valid JSON (15, 8, 20 and 13 runs respectively). The defect-hit metric is therefore, in practice, a review-parse rate, and the H gate failure comes from 20 unparseable reviews. No review in any arm returned `verdict: approve` (0/160), so the verdict is not a discriminating signal here. The cause of the unparseable reviews was not analysed in the main phase; see section 7a.

## 7a. Post-hoc diagnosis of the unparseable reviews (descriptive; added after results)

Script: `stage2_json_diagnosis.py` (reads `full_s2_outputs.jsonl` and `full_s2_scored.jsonl`; no network). It does not change any scored value, gate or threshold.

All 56 unparseable reviews start as a JSON object. In 52 of them the failure is the same: the characters that close the `findings` array just before the `"summary"` key are wrong. The model wrote `]],` (23), `]),` (20), `]",` (7) or `].,` (2) instead of `],`. The other 4 fail elsewhere (for example a trailing comma before the closing brace, and one unterminated string in an arm A run, `T07-A-r05`). Truncation is not the cause: every call ended with `end_turn`.

| arm | invalid reviews (of 40) | malformed closer before `summary` | other | recovered by tail repair | defect-hit, strict (gate) | defect-hit after tail repair |
|---|---|---|---|---|---|---|
| control | 15 | 13 | 2 | 15 | 25/40 | 40/40 |
| A | 8 | 6 | 2 | 8 | 32/40 | 40/40 |
| H | 20 | 20 | 0 | 20 | 20/40 | 40/40 |
| AH | 13 | 13 | 0 | 13 | 27/40 | 40/40 |

Tail repair = cut the text at the last `"summary"` key, force-close the findings list, and re-add a placeholder summary; then apply the unchanged Stage 1 `defect_hit` check.

Separately, 53 reviews are valid JSON but lack a `summary` key (44) or name it `" summary"` (9). These count against the format rate (section 3), not against defect-hit.

Reading, with limits:
- Every one of the 160 reviews names the planted defect once the closing brackets are repaired. The defect-hit gate difference (H fails, A and AH pass) therefore comes from JSON formatting, not from missed defects.
- This does not show equal review quality. The planted-defect check is one regex per ticket, 100% of matches is suspiciously lenient, `verdict: approve` never occurred (0/160), and the blind judge has not been run.
- The repair rule was written after seeing the failures, so it is post-hoc. It is evidence about the metric, not a pre-registered result.
- Implication for a next run: add a one-line fix for the findings-array closer (or request structured output) in the review prompt before drawing quality conclusions between arms.

## 8. Caveats

- **Naive-chaining baseline.** Control resends the full ticket and every raw upstream output to every stage. The total-token reductions (A 15%, H 45%, AH 50%) are measured against that baseline, not against a sensible pipeline. Against a well-engineered chain they may be smaller; this was not tested.
- **Eight tickets.** Effects apply to this ticket set. The five reps of a ticket are correlated, and the cluster bootstrap has only 8 clusters, so the CIs are likely too narrow.
- **Coarse defect-hit metric.** One planted defect per diff, matched by regex on the right file. It counts only parseable reviews (section 7), and the regex may be lenient: 100% of parseable reviews match. Other findings are counted in `other_findings` but are not analysed here.
- **Arm A text.** It is a coding-agent instruction (smallest diffs, one-line replies) applied to JSON-producing stages. Its effect here is not a clean test of terse output.
- **Single sample per cell.** Each cell is one sample per rep. Reps are independent samples (no seed on Haiku 5.5, temperature fixed at 1), so the 40 units per arm are not independent draws of tickets.
- **No caching in phase A.** W has no cache terms, and no prompt-cache effect is measured. Phase B is not run.
- **Format gate uninformative.** The control format rate (0.30) is below the 0.5 threshold, so the format component of the gate is not applied, and the only gate is defect-hit, which is the parse-rate issue in section 7.
- **Scoring timing.** The failure-reason tally and the parseability breakdown (sections 3 and 7) were computed after the first scoring pass. Neither changed a check or threshold. The scorer deviations (section 17) were committed before any Stage 2 result was computed.
- **Stage 1 comparison.** The Stage 1 numbers come from `summary.txt` and the same method, which reproduces them. Stage 1 used a local model with a different tokenizer, so token counts are not directly comparable across stages; only the ratios are compared.
- **Dollars.** Dollars use the Haiku 5.5 base-tier prices in `stage2_prices.json`. Cache prices are unused in phase A. Reconciled after the run: the Console Cost page for the benchmark key shows $0.37 (input about $0.127, output about $0.238, no cache cost) against $0.364969 computed here, consistent to rounding; the account balance moved by about $0.36. See `STAGE2_PREREGISTRATION.md` section 16.

## 9. Files

- `stage2_score.py` (scoring, bootstrap, Stage 1 reproduction check), `stage2_analysis.py` (tables), `stage2_export_blind.py` (judge packets)
- `stage2_json_diagnosis.py` (post-hoc diagnosis, section 7a)
- `full_s2_scored.jsonl` (per-run scores), `blind_s2/` (160 packets)
- `STAGE2_PREREGISTRATION.md` section 17 (scoring deviations)
