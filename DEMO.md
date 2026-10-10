# Demo: measure first, then optimize

Numbers come from `experiments/sdlc_census/REPORT.md` and `experiments/nested_trace/REPORT.md`.

## Executive version (5 lines)

1. We measured where agent tokens and weighted cost go before building any compressor (assumed prices: uncached 1, cached 0.1, output 4).
2. On bug-fix work, all context levers together cap at about 10% of weighted cost; output is 44-45%. Test/CI output is 5.0-5.8%, file reads 2.6-4.0%.
3. On read-heavy work, file reads are 68% and cache-prefix breaks 22.2%, but that is 2 sessions.
4. In a naive 3-task nested chain (local 9B model, payload size and use only, not quality), 29.1% of tokens and 22.9% of weighted cost was handoff payload the next agent did not use. That is an upper bound for naive chaining, not a saving.
5. Aegis = 1 task; opencode = 2 sessions; nested trace = local 9B model, 3 tasks, naive baseline, payload size/use only. No savings were achieved. The 30-40% target is untested, and the census suggests context compression cannot reach it on bug-fix work.

## Engineer version

1. Run the census: `.venv/Scripts/python.exe -m tokenopt.census experiments/agent_benchmark/traces`. Read the ranked lever list; values are shares at 100% removal.
2. Change prices: `--cached <x> --output <y>`.
3. Handoff measurement: each handoff row carries `handoff = {"payload_tokens", "used_tokens"}`. A payload line counts as used if at least 50% of its distinctive tokens appear in the receiver's output or tool-call args (`experiments/nested_trace/measure_handoff.py`).
4. Run `python -m tokenopt.census experiments/nested_trace/traces`. It shows a lower handoff figure (22.1% of tokens) because it counts each payload once. The report's 29.1% includes re-billing on each receiver turn.
5. Re-run the nested trace: `experiments/nested_trace/run_workflow.py`, then `measure_handoff.py`. Cost: 36 calls (12 per task), about 5 minutes model time, local Ollama qwen3.5:9b, $0. A re-run gave 27.9% / 22.0% (34 calls): same range, not identical.
6. Your own data: agent-trace/v1 JSONL with `messages`, or Aegis run dirs. See README.

## Where it fails

- Handoff: n=3, one run each, naive full-forwarding baseline, and a small model that repeated the same read in t1 and t2. Threshold range 22.5-34.7% of tokens.
- The match rule is not hand-validated; common identifiers inflate "used", paraphrase deflates it.
- Cached tokens are unknown, so all prompt counts as uncached.
- Bug-fix numbers come from one task; read-heavy numbers from two sessions.
- Handoff rows overlap tool-result rows; do not add them.

## What to try next (not started)

- B: terse structured agent outputs and turn reduction under the 95% quality gate.
- C: file-read outline handler, only after a larger read-heavy trace set.

## Limits

No savings were achieved. No answer quality was graded. The 30-40% target is untested. Handlers are deferred pending a decision. Do not extrapolate beyond local models and short synthetic SDLC tasks.
