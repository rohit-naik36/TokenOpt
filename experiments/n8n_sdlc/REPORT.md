# Report: n8n SDLC workflow benchmark (output discipline x structured handoff)

Pre-registered in `PREREGISTRATION.md` (with Amendment 1). All numbers below come from `summary.txt` (`score.py` on `runs.jsonl`) plus the blind-judge section appended by `judge_analysis.py`. Local model `qwen3.5:9b` through n8n; 8 synthetic tickets x 5 reps x 4 arms = 160 runs, 160 completed, 0 harness errors. Nothing here is pushed.

Arms: **control** = naive chaining (full ticket + raw upstream text); **A** = control plus the output-discipline instruction; **H** = each stage receives only the structured fields it needs; **AH** = both.

## 1. Results

Ratio arm/control (sum over paired ticket-rep units), 95% ticket-clustered percentile bootstrap (8 clusters, 10,000 resamples, seed 20261015).

| arm | output tokens | total tokens | W = prompt + 4 x output |
|---|---|---|---|
| A | 0.82 [0.77, 0.87] | 0.94 [0.91, 0.96] | 0.90 [0.86, 0.93] |
| H | 0.90 [0.81, 0.98] | 0.60 [0.57, 0.62] | 0.71 [0.66, 0.75] |
| AH | 0.79 [0.74, 0.84] | 0.59 [0.58, 0.61] | 0.67 [0.64, 0.69] |

Sensitivity (W with output weight 1 / 8): A 0.94 / 0.87, H 0.60 / 0.77, AH 0.59 / 0.71. Mean tokens per run (prompt + output): control 7597, A 7129, H 4548, AH 4505. Wall time per run: 47 / 40 / 42 / 38 s (includes model reload).

Under the section 8 decision rules every CI for every endpoint lies entirely below 1, so a reduction is shown for all three arms on all three endpoints. A's W upper bound (0.93) is close to the 0.90 to 1.10 band, so A's cost effect is small; H and AH are large. Most of H's saving is prompt tokens (it sends fewer fields), and H's output-token CI upper bound is 0.98, so that part is barely below 1. The CIs rest on 8 tickets and are likely too narrow (Amendment 1).

Deterministic quality (n = 40 runs per arm):

| arm | all 5 stages ok | defect hit | composite pass (Wilson 95%) | composite, repaired-brace variant |
|---|---|---|---|---|
| control | 3 | 26/40 (0.65) | 2/40 (0.01 to 0.17) | 21/40 |
| A | 4 | 25/40 (0.625) | 3/40 (0.03 to 0.20) | 16/40 |
| H | 11 | 29/40 (0.725) | 9/40 (0.12 to 0.38) | 28/40 |
| AH | 11 | 24/40 (0.60) | 11/40 (0.16 to 0.43) | 23/40 |

Almost every format failure is the `plan` stage missing its final closing brace (`not_json`), in all arms; this is why the strict format rate is very low in control.

Defect hits per ticket (of 5 reps; control, A, H, AH): T01 4,4,4,3; T02 5,2,3,4; T03 4,3,4,3; T04 2,2,5,5; T05 4,2,1,2; T06 1,5,4,2; T07 5,5,5,5; T08 1,2,3,0. Swings of 3 to 4 hits on a single ticket go both ways, so the per-arm hit rates are noisy.

## 2. Quality gate, exactly as pre-registered

Gate (section 6): an arm passes if both its format rate and its defect-hit rate are at least 95% of control's. Control's format rate is 0.07 (< 0.5), so the format component was declared uninformative in advance.

| arm | format gate | defect-hit gate | outcome |
|---|---|---|---|
| A | n/a | 0.62 vs 0.65, PASS | passes (on defect-hit only) |
| H | n/a | 0.72 vs 0.65, PASS | passes (on defect-hit only) |
| AH | n/a | 0.60 vs 0.65 (0.923 of control), **FAIL** | fails |

Per section 8, a cost reduction counts as promising only if the gate passes. So A and H are reported as reductions with a passing gate, and **AH is reported as a quality-cost trade-off**: the largest token saving, with a defect-hit rate below the 95% threshold (24 of 40 against 26 of 40, a two-run difference). A "pass" at n = 40 means "not distinguishable at this n", not equivalence. The composite pass rate is not the gate; it is higher for H and AH than for control only because they produce fewer malformed `plan` outputs.

## 3. Blind judge (secondary, never merged with the gate)

Scores 0 to 10 per `judge_rubric.md`; mean per arm and ratio to control (same pairing and bootstrap as above):

| arm | mean total | ratio vs control (total) | review-criterion ratio | secondary gate (>= 95% of control) |
|---|---|---|---|---|
| control | 6.50 | | | |
| A | 6.42 | 0.99 [0.91, 1.10] | 0.93 [0.71, 1.22] | PASS |
| H | 6.25 | 0.96 [0.87, 1.07] | 0.98 [0.66, 1.42] | PASS |
| AH | 5.92 | 0.91 [0.79, 1.05] | 0.87 [0.61, 1.18] | FAIL |

The judge's direction agrees with the deterministic gate for AH (lowest score, fails) but the CIs include 1 for every arm, so this does not show a quality difference by itself. Sanity check: the judge's review score averages 1.90 where the deterministic match rule found the defect and 0.59 where it did not, so the judge signal is related to defect-hit. Mean judge total by ticket varies from 8.05 (T04) to 4.20 (T08).

**Blindness.** The judge session opened only `blind/*.md` packets and `judge_rubric.md`. It never opened `blind_map.json`, `runs.jsonl`, `scored.jsonl`, `summary.txt`, the run log or git history. Scores were written to `judge_scores.jsonl` (in batches of 20) before the map was opened. Two caveats:
1. For most packets the judge read only the stage outputs (`sed` from "Stage output: requirements"), not each packet's ticket and diff sections. It relied on ticket details seen in other packets of the same ticket. The judge score is therefore a coarse secondary signal; **defect-hit is the primary quality signal**.
2. Output style (A terse, H shorter handoffs) may reveal the arm even to a blind judge.

## 4. Limitations

- **Naive-chaining baseline.** Control resends the full ticket and every raw upstream output to every stage, which is deliberately wasteful. H's 40% total-token saving is measured against that baseline, not against a reasonably engineered pipeline.
- **8 tickets.** Effects are conditional on this ticket set; the 5 reps of a ticket are correlated. The clustered bootstrap has only 8 clusters (coarse, probably too narrow) and the Wilson intervals treat runs as independent.
- **Weak defect-hit metric.** One planted defect per diff, matched by regex on the right file; it can over- or under-count, ignores verdict, and counts other findings only as `other_findings` (control 0.85, A 0.60, H 0.75, AH 0.83 per run). Reviews that approved the diff: 5, 7, 7, 9 of 40 (control, A, H, AH).
- **No caching modeled.** W uses uncached input 1 and output 4 with no cached-token term; the model was unloaded before every run. With provider prompt caching, control's repeated prefixes would be cheaper and H's relative advantage would shrink. Wall time includes model reload.
- **A wording on JSON stages.** The arm-A text is a coding-agent instruction (smallest diffs, one-line replies) applied to JSON-producing stages. It is byte-identical to the otl-001 text, so its effect here is not a clean test of "terse output".
- **Repaired-brace variant.** Strict scoring was kept; the repaired-brace column (accepting output that only lacks closing brackets) is reported alongside and changes the composite ordering: control 21, A 16, H 28, AH 23 of 40. The workflow itself repairs braces when feeding H, which helps H only. The `format: json` decision in section 9 of the pre-registration was not taken; the run was as registered.
- **Judge.** A single pass by Claude inside Claude Code (no API key, temperature not controllable), so non-deterministic. My own scoring was not perfectly consistent across the 160 packets (for example how harshly invented requirements or release-note framing were penalized drifted slightly), which adds noise.
- **Other.** Local 9B model, synthetic tickets written by the experimenter, no length-matched placebo, H changes the input format as well as its content, so quality differences cannot be attributed to token count alone. Nothing here transfers to Claude models or real tickets.

## 5. Deviations

None recorded after the first full-run row in the files this report was built from. The only post-hoc change is analysis-side: `summary.txt` was converted from UTF-16 to UTF-8 (content unchanged) before the judge section was appended.

## 6. Files

`runs.jsonl`, `scored.jsonl`, `summary.txt` (score.py output + judge section), `blind/` (160 packets), `blind_map.json`, `judge_rubric.md`, `judge_scores.jsonl`, `judge_analysis.py` (join, ratios, bootstrap), `run_full.log`.
