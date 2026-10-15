# n8n SDLC workflow benchmark

Measure-first test of how much cost a 5-stage SDLC chain saves when its stages hand off differently. Results are cost evidence on a small synthetic set; read the limits below before quoting them.

## What it runs

- **Chain (n8n workflow):** triage, requirements, plan, review, release note. Each stage returns one JSON object.
- **Data:** 8 synthetic tickets in `tickets/`, each with one planted defect in a diff (ground truth in `tickets/ground_truth.json`, read only by the scorer).
- **Arms:**
  - `control`: naive chaining, every stage receives the ticket and all raw upstream output.
  - `A`: output discipline (a short instruction that keeps stage outputs terse).
  - `H`: structured handoff (each stage receives a compact structured summary, not full text).
  - `AH`: both.
- **Design:** 8 tickets x 4 arms x 5 reps = 160 runs, 800 stage calls, per model. Interleaved order.
- **Stage 1:** local `qwen3.5:9b` via Ollama (`REPORT.md`). **Stage 2:** `claude-haiku-5-5` via the Messages API, no caching (`STAGE2_RESULTS.md`).

## Results at a glance

| arm | Stage 1 weighted cost vs control | Stage 2 dollars vs control [95% CI] |
|---|---|---|
| A | 0.90 | 0.80 [0.79, 0.81] |
| H | 0.71 | 0.75 [0.73, 0.77] |
| AH | 0.67 | 0.60 [0.58, 0.62] |

Stage 2 cost: $0.364969 for all 160 runs. Weighted cost W = uncached input x1 + cache read x0.1 + output x4. Ratios are ticket-clustered bootstrap (10,000 resamples, seed 20261015). Quality gate: defect-hit rate at least 95% of control. Deterministic gate in Stage 2: A pass, H fail, AH pass; the H failure is driven by invalid JSON in the review stage (see `STAGE2_RESULTS.md` section 7a), not by missed defects. Blind judge score vs control: A 1.01, H 0.95, AH 0.96 (see section 6).

## Limits

- 8 synthetic tickets; effects may not transfer to production traffic.
- Baseline is naive chaining, not a tuned pipeline; savings against a better baseline may be smaller.
- Defect-hit is a regex check on one planted defect; it is coarse.
- Quality was checked by one blind LLM-judge pass (claude-sonnet-4-6, temperature 0) that scores near ceiling, so it discriminates weakly; H and AH sit at about 95% of control on it.
- Arm A's text was written for coding agents and applied to JSON stages.

## Re-running Stage 2

Requires Docker, Python 3.10+, and an Anthropic API key. Never commit keys; the key lives only in the n8n container environment.

```bash
export ANTHROPIC_API_KEY=...        # your own key, never written to a file
export BENCH_WEBHOOK_TOKEN=...      # any random string; gates the webhook
docker run -d --name n8n-sdlc -p 5678:5678 --memory 1500m \
  --add-host=host.docker.internal:host-gateway -v n8n_sdlc_data:/home/node/.n8n \
  -e N8N_SECURE_COOKIE=false -e N8N_DIAGNOSTICS_ENABLED=false \
  -e EXECUTIONS_DATA_SAVE_ON_SUCCESS=none -e EXECUTIONS_DATA_SAVE_ON_ERROR=none \
  -e N8N_RUNNERS_ENABLED=false -e N8N_BLOCK_ENV_ACCESS_IN_NODE=false \
  -e ANTHROPIC_API_KEY -e BENCH_WEBHOOK_TOKEN n8nio/n8n:latest
docker cp experiments/n8n_sdlc/workflow_stage2.json n8n-sdlc:/tmp/workflow_stage2.json
docker exec n8n-sdlc n8n import:workflow --input=/tmp/workflow_stage2.json
docker exec n8n-sdlc n8n publish:workflow --id=sdlcbench0000002
docker restart n8n-sdlc
cd experiments/n8n_sdlc
python stage2_runner.py --tickets T01,T02,T03,T04,T05,T06,T07,T08 --reps 5 \
  --arms control,A,H,AH --model claude-haiku-5-5 --caching none --cap 1.50 \
  --out my_runs.jsonl --outputs my_outputs.jsonl
```

`--cap` is a dollar stop rule (a run can overshoot by at most one run). A dry run with no network: add `--dry-run`. Then score with `stage2_score.py` and tabulate with `stage2_analysis.py`.

Check the Anthropic pricing page and `stage2_prices.json` before relying on dollar figures; they are the prices used for this run.

## Files

`STAGE2_PREREGISTRATION.md` (plan, written before any API call), `STAGE2_RESULTS.md` (results), `PREREGISTRATION.md` and `REPORT.md` (Stage 1), `stage2_runner.py`, `stage2_cost.py`, `stage2_score.py`, `stage2_analysis.py`, `stage2_json_diagnosis.py`, `workflow_stage2.json`, `prompts/`, `tickets/`, `full_s2_*.jsonl` (raw runs, outputs, scores), `blind_s2/` (judge packets).
