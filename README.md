# TokenOpt

[![CI](https://github.com/rohit-naik36/TokenOpt/actions/workflows/ci.yml/badge.svg)](https://github.com/rohit-naik36/TokenOpt/actions/workflows/ci.yml)

TokenOpt is an AI prompt-optimization SDK and proxy. It applies preservation-aware, deterministic transformations to LLM prompts (whitespace/filler removal, duplicate pruning) behind a fidelity Validator, with semantic caching, model routing, and observability.

## Measured savings

These are the current, evidence-based numbers. Do not cite higher figures.

| Workload | Measured input-token reduction | Notes |
| --- | --- | --- |
| AAVA agent definitions (4,343) | **~0.7–0.9%** (median 0%) | deterministic optimizer, o200k estimate — see [benchmark](evaluation/AAVA_STATIC_AGENT_BENCHMARK.md) |
| SWE-bench Lite problem statements (300) | **0.23%** (median 0%) | dense technical prose |
| SWE-agent trajectories (20, per LLM call) | **~1.8%** optimizer (0 rollbacks) | recorded runtime context |

The optimizer's prose compression is small on real, dense prompts. The large levers on agent workloads are **provider prompt caching** (the repeated system+demonstration prefix was **~42%** of input tokens on the trajectories measured — cache-eligible, realized savings depend on the provider's cache discount) and **stale-observation elision** (**~24%** upper bound, lossy). Both are measured estimates on 20 trajectories, not billing, and are not yet implemented. Earlier "15–20%" / "~24% compression" style claims were from synthetic prompts and are not representative.

## Census and method: measure first, then optimize

TokenOpt includes an offline census tool that shows where an agent workload's tokens and weighted cost go, then ranks which levers are worth building. No savings from it have been achieved yet (see "What this does not show"). Walkthrough: [DEMO.md](DEMO.md).

### Run it

```bash
python -m tokenopt.census <trace dir>
```

Price assumptions are printed and can be changed: uncached input 1, cached input 0.1, output 4 (`--cached`, `--output`). Real output on the opencode traces:

```
Price assumptions (relative to uncached input): uncached 1, cached 0.1, output 4.0

== traces: 2 sessions, 15 turns, 433459 tokens ==
component                 tok%   cost%  first-entry cost%  re-billed cost%
static prefix            34.1%   22.7%
assistant history         1.4%    1.5%
tool: file reads         63.8%   67.9%              41.9%            26.0%
output                    0.7%    7.9%
cache-prefix breaks: 2, cost  22.2% of weighted cost; avg turn =  15.0% of its session
handoff payload: UNKNOWN (no rows with workflow fields + handoff object)
levers ranked by upper bound at 100% removal (cost% / tok%):
  1. file-read (outline) handler     [handler]  67.9% /  63.8%
  2. cache-prefix-break avoidance    [cache discipline]  22.2% /   0.0%
  3. one-turn reduction (avg turn)   [turn reduction]  15.0% /  15.0%
  4. output-token reduction          [turn reduction]   7.9% /   0.7%
  5. test/CI/build output handler    [handler]   0.0% /   0.0%
  6. JSON/log handler                [handler]   0.0% /   0.0%
  7. diff handler                    [handler]   0.0% /   0.0%
  8. handoff payload                 [handoff contract] UNKNOWN / UNKNOWN
```

Command used: `.venv/Scripts/python.exe -m tokenopt.census experiments/agent_benchmark/traces`.

### Data, and its limits

| Set | Size | Notes |
|---|---|---|
| Aegis bug-fix controls | 1 task (T1), 30 control sessions, 446 turns including treatment runs | local model; one run excluded as misaligned |
| opencode | 2 read-only sessions, 15 turns | one session has the cache anomaly |
| Nested trace | 3 tasks, 36 calls | local qwen3.5:9b; measures handoff payload, not answer quality |

Sources: `experiments/sdlc_census/REPORT.md`, `experiments/nested_trace/REPORT.md`.

### Findings (upper bounds at 100% removal, not savings)

- Bug-fix work (Aegis controls, weighted cost): test/CI output 5.0-5.8%, file reads 2.6-4.0%, JSON/logs and diffs absent from the data. All context levers combined are 7.6-9.8%, about 10%. Output is 44-45%; one average turn is 12-15%.
- Read-heavy work (opencode, n=2): file reads 68% of weighted cost; cache-prefix breaks 22.2% pooled (36.3% in one session), cause undiagnosed.
- Handoff in a naive nested chain (n=3), an upper bound for naive chaining and not a saving: unused, re-billed payload is 29.1% of tokens and 22.9% of weighted cost. Range over the match threshold: 22.5-34.7% of tokens, 17.7-27.3% of cost. Cached tokens are unknown (Ollama does not report them), so all prompt counts as uncached, which overstates context weight.

### Caveats, stated plainly

- Aegis bug-fix numbers come from **one task** (T1) on a local model.
- opencode numbers come from **two sessions** (15 turns), no outcome label.
- The nested trace is a **local 9B model (qwen3.5:9b), 3 tasks, one run each, naive full-forwarding baseline**. It measures **payload size and use only, not answer quality**.
- **29.1% of tokens / 22.9% of weighted cost is an upper bound for naive chaining, not a saving.** It is the unused, re-billed share of what a naive orchestrator forwards; a real handoff contract would remove part of it, and a competent baseline has less to remove.

### What this does not show

- No savings were achieved. Every figure above is a ceiling or a share, not a measured reduction.
- The 30-40% target is untested. On bug-fix work the census suggests it is not reachable from context compression: the context levers cap near 10%, and reaching 25% would need about 46% of output cost removed, which changes what the agent writes.
- Handlers are deferred pending a decision.
- Small n, one task for bug-fix, local models, short synthetic tasks. Do not extrapolate to other workloads.
- The handoff baseline is deliberately naive (full forwarding); a competent baseline would show less bloat. The "used" match rule is an unvalidated estimate. Handoff rows overlap tool-result rows; do not add them.

### What to try next (not started)

- **B. Terse structured agent outputs and turn reduction**, under the 95% quality gate (end-to-end outcome at least 95% of baseline, judged on held-out tasks). Targets the levers the census ranks highest on bug-fix work: output (44-45% of weighted cost) and turns (12-15% each). Needs approval and a spend plan.
- **C. File-read outline handler**, only after a larger read-heavy trace set exists. The 68% ceiling comes from 2 sessions with no outcome label, and outlines changed agent decisions in earlier tests.

### On your own traces

Input is a directory of agent-trace/v1 JSONL (one request/response per row, with `messages`) or Aegis run dirs (`events.jsonl` plus `raw/stream.jsonl`). For multi-agent runs, add optional row fields `workflow_id`, `parent_workflow_id`, `agent`, `step`, and `handoff = {"payload_tokens": int, "used_tokens": int}`. Without them the handoff line prints UNKNOWN. `--json <file>` also writes results.

### Reproduce

- Census report: `experiments/sdlc_census/census.py` writes `results/census.json`; test `test_census.py`.
- Nested trace: `experiments/nested_trace/run_workflow.py` (needs local Ollama with qwen3.5:9b), then `measure_handoff.py`; results in `results/handoff.json`; test `test_measure.py`.
- `python -m tokenopt.census experiments/nested_trace/traces` prints 22.1% of tokens for handoff because it counts each payload once; the 29.1% above includes re-billing.
- Reproduction checked: `census.py` reproduces `census.json` byte for byte. Re-running the nested trace gave 34 calls and bloat 27.9% of tokens / 22.0% of weighted cost versus the reported 29.1% / 22.9% (the local model is not fully deterministic; rerun kept in `experiments/nested_trace/rerun/`).
- Walkthrough: [DEMO.md](DEMO.md).

---

## Monorepo Architecture

This repository consolidates the TokenOpt product ecosystem into a unified monorepo:

| Folder | Component | Description |
| ------ | --------- | ----------- |
| [`tokenopt-proxy/`](tokenopt-proxy/) | **HTTP Enterprise Proxy** | Production FastAPI service (`v2.0`) with async embeddings, circuit breaker provider router, PostgreSQL audit trail, Redis cache, and Kafka event streamer. See [Proxy README](tokenopt-proxy/README.md). |
| [`tokenopt-optimizer/`](tokenopt-optimizer/) | **Optimizer Engine** | Standalone, embeddable `tokenopt_optimizer` engine with response fidelity validation, batch optimization, TTL LRU cache, and tokenizers. See [Optimizer README](tokenopt-optimizer/README.md). |
| [`tokenopt-sdk/`](tokenopt-sdk/) | **Client SDK (`v0.1.0`)** | Drop-in `tokenopt` client SDK for OpenAI, Anthropic, and local models (Ollama/vLLM/llama.cpp). See [SDK README](tokenopt-sdk/README.md). |

```
.
├── tokenopt-proxy/        # FastAPI HTTP Proxy service, Dockerfile, Terraform, & docs
├── tokenopt-optimizer/    # Standalone Python optimizer engine
└── tokenopt-sdk/          # Published client SDK (v0.1.0 snapshot) + .ai/ specs
```

---

## Quick Start — Proxy & Enterprise Platform

### Running the Proxy (Local)

```bash
cd tokenopt-proxy
pip install -r requirements.txt
set JWT_SECRET="demo-secret-key-for-presentation-only"
uvicorn tokenopt_proxy_v2:app --host 0.0.0.0 --port 8000
```

### Running the Demo Script

```bash
cd tokenopt-proxy
set JWT_SECRET="demo-secret-key-for-presentation-only"
python demo.py --no-llm
```

### Docker Build

```bash
cd tokenopt-proxy
docker build --build-context tokenopt_sdk=../tokenopt-optimizer -t tokenopt-proxy:latest .
```

---

## Quick Start — TokenOpt Client SDK (`v0.1.0`)

The SDK provides drop-in replacement wrappers for OpenAI and Anthropic clients:

```python
from tokenopt import OpenAI

# Drop-in replacement for standard OpenAI client
client = OpenAI()

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Explain quantum computing in simple terms..."}],
)
print(response.choices[0].message.content)
print("Metrics:", client.get_metrics_summary())
```

---

## Testing & Quality Assurance

Run the test suite for any component:

```bash
# Test the HTTP Proxy & Hardening Suite (82 tests)
cd tokenopt-proxy && python -m pytest tests/ -v

# Test the Standalone Optimizer Engine
cd tokenopt-optimizer && python -m pytest tests/ -v

# Test the Client SDK
cd tokenopt-sdk && python -m pytest tests/ -v
```

---

## Licensing

This repository follows an **Open-Core Dual-Licensing** model:

- **TokenOpt Enterprise Platform (`tokenopt-proxy/`)**: Licensed under the **TokenOpt Enterprise Commercial License** ([tokenopt-proxy/LICENSE](tokenopt-proxy/LICENSE)). Commercial / paid software; production use requires an enterprise license agreement or authorized production pilot agreement.
- **Client SDK (`tokenopt-sdk/`)**: Licensed under the **MIT License** ([tokenopt-sdk/LICENSE](tokenopt-sdk/LICENSE)). Free for embedding into client applications.
- **Optimizer Engine (`tokenopt-optimizer/`)**: Licensed under the **MIT License** ([tokenopt-optimizer/LICENSE](tokenopt-optimizer/LICENSE)). Standalone embeddable core.

See [LICENSE](LICENSE) for the full monorepo licensing summary.
