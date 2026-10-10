# Nested-workflow handoff-bloat trace (payload size vs use)

**This measures payload size and use. It is NOT a quality comparison; no answer quality was graded.** n = 3 tasks, one run each (temp 0, seed 7): anecdotal. Source: `run_workflow.py`, `measure_handoff.py`, `results/handoff.json`, traces in `traces/`. Tests: `test_measure.py` (4 pass).

## Setup
Local Ollama qwen3.5:9b only, $0. Budget stated before the run: <=80 calls, <=90 min. Used: 36 calls (12 per task), about 5 min model time, 0 failures. num_ctx 8192, think=false, num_predict 700.
Workflow per task: A (tools read_file/grep/list_dir/run_pytest, max 5 turns) -> B plan -> nested B1 (writes a test) -> B2 (runs it) -> B finish -> C report. Naive handoff: the next agent's first prompt gets the previous agent's full final message plus all gathered tool outputs (tool output capped at 2000 chars). No compression anywhere. Tasks: t1 explain a cache TTL test, t2 add a test for an untested helper, t3 triage an injected failing test.
Turns per agent (each task): A 5, B 2, B1 2, B2 2, C 1.

## Results (36 calls, 15 handoffs)
Provider tokens: 40,909 prompt + 4,020 output = 44,929. Weighted cost 56,989 with uncached 1, output 4; cached tokens are UNKNOWN (Ollama does not report them), so ALL prompt is treated as uncached. This overstates the weight of context against a provider with prefix caching.

| | tokens | weighted cost |
|---|---|---|
| Gross payload (used + unused, re-billed each receiver turn) | 39.1% | 30.9% |
| Handoff bloat (unused, re-billed), threshold 0.5 | 29.1% | 22.9% |
| Bloat, threshold 0.25 / 1.0 | 22.5% / 34.7% | 17.7% / 27.3% |

Per task bloat / gross (tokens): t1 32.5% / 42.9%, t2 22.3% / 28.4%, t3 29.1% / 41.0%. Worst handoffs: B1->B2 uses almost nothing (4/303 tokens in t2, 0/104 in t3); B->B1 re-forwards A's whole payload and uses about 10-25%.
`python -m tokenopt.census experiments/nested_trace/traces` shows a lower figure (22.1% of tokens) because it counts each payload once; the table above includes re-billing.

## Matching rule and its error (estimate)
A payload unit is a non-blank line; it counts as used if >=50% of its distinctive tokens (identifiers of 3+ chars, numbers of 2+ digits, lowercased; stop-words, Python keywords and tokens in the receiver's system prompt/task removed) appear in the receiver's assistant content or tool-call args. Lines with no distinctive token are neutral. Common identifiers inflate "used"; paraphrase deflates it. Not hand-validated; the threshold sensitivity is the only error bound. Tokens are o200k, not Ollama's.

## Caveats
- The baseline is deliberately naive (full forwarding). A competent baseline would show less bloat, so this is the upper end of what a handoff contract could remove.
- In t1 and t2, Agent A spent all 5 turns repeating the same read_file call and ended with an empty final message (small-model behavior, untuned). The A->B payload there is mostly raw tool output.
- Bloat overlaps the tool-result and history rows of the census; do not add the rows.
- Small model, short synthetic tasks, 3 runs, no cached-token data.

## Reproduction check (2026-10-10)
`run_workflow.py` was re-run (temp 0, same seed): 34 calls (t3 took 10 calls instead of 12), `measure_handoff.py` gave bloat 27.9% of tokens / 22.0% of weighted cost (gross 39.1% / 30.8%). Close to the reported 29.1% / 22.9% but NOT byte-identical: the local model is not fully deterministic. The rerun is kept in `rerun/`; the figures above remain the reported run. `run_workflow.py` also leaves a scratch repo copy in `_ws/` (generated, do not commit).
