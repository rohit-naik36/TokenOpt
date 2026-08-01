# TokenOpt SDK

[![CI](https://github.com/rohit-naik36/TokenOpt/actions/workflows/ci.yml/badge.svg)](https://github.com/rohit-naik36/TokenOpt/actions/workflows/ci.yml)

Token and prompt optimization for LLM clients — a **drop-in replacement** for
OpenAI/Anthropic (plus local models via Ollama/vLLM/llama.cpp) that
automatically reduces token usage and cost.

- **Cost reduction** — prompt compression, summarization, model routing
- **Context management** — semantic caching, RAG chunk optimization
- **Latency** — cheap-model routing for simple queries, cache hits avoid API calls
- **Quality preservation** — quality-aware routing and similarity-based few-shot selection

All optimization is **best-effort and fails open**: an optimization error
never blocks the underlying request.

## 5-Minute Quick Start

1. **Clone the repository**

   ```bash
   git clone https://github.com/rohit-naik36/TokenOpt.git
   cd TokenOpt
   ```

2. **Create a virtual environment** (Python ≥ 3.10)

   ```bash
   python -m venv .venv
   ```

   Then activate it — macOS/Linux: `source .venv/bin/activate` ·
   Windows: `.venv\Scripts\activate`

3. **Install the package**

   ```bash
   pip install -e .
   ```

4. **Install optional extras if needed** — e.g. native Ollama support:

   ```bash
   pip install -e ".[local]"
   ```

5. **Set your API key** (OpenAI for this quick start)

   ```bash
   export OPENAI_API_KEY=sk-...           # macOS/Linux
   # PowerShell:  $env:OPENAI_API_KEY = "sk-..."
   ```

6. **Run the example**

   ```bash
   python examples/quickstart.py
   ```

7. **Expected output** — a readable metrics block (not raw JSON):

   ```
   Request metrics:
     Model:           gpt-4o-mini
     Cache hit:       No
     Compression:     attempted / no reduction (0 tokens, 0.0%)
     Tokens:          27 -> 27 (+7 output)
     Latency:         total 566.4 ms | model 393.8 ms | TokenOpt overhead 172.6 ms
     Estimated cost:  $0.000008
     Response:        TokenOpt is a drop-in SDK that optimizes LLM prompts...
   Aggregated metrics:
     Requests:            1
     Cache hit rate:      0.0%
     ...
   ```

   **What a successful run looks like:** the script prints the response plus
   a per-request metrics block showing the model actually used (note the
   router may pick `gpt-4o-mini` for simple queries), cache status,
   compression outcome, latency split, and estimated cost. If you see a
   `Request metrics:` block and a response, TokenOpt is working.

   See `examples/` for runnable value demonstrations — compression OFF vs ON,
   cache miss → hit, conversation summarization, model routing with reasons,
   and observability — plus `docs/UAT.md` for the full acceptance checklist.

## Installation

> ⚠️ TokenOpt is **not on PyPI yet** (v0.1.0 is pre-release). Install from
> GitHub until v0.1.0 is published.

```bash
# From GitHub (regular use)
pip install git+https://github.com/rohit-naik36/TokenOpt.git

# Or clone + editable install (recommended for development)
git clone https://github.com/rohit-naik36/TokenOpt.git
cd TokenOpt
pip install -e .
```

**Core install** (OpenAI + Anthropic providers, routing, compression,
summarization, in-memory caching, RAG, few-shot, metrics):

| Extras | Enables | Command |
|--------|---------|---------|
| (none) | core as above | `pip install -e .` |
| `[local]` | native Ollama support | `pip install -e ".[local]"` |
| `[cache]` | Redis-backed semantic cache | `pip install -e ".[cache]"` |
| `[semantic]` | sentence-transformers embeddings | `pip install -e ".[semantic]"` |
| `[compression]` | LLMLingua compression | `pip install -e ".[compression]"` |
| `[all]` | everything above | `pip install -e ".[all]"` |
| `[dev]` | test/lint/type/audit tools | `pip install -e ".[dev]"` |

Requires **Python ≥ 3.10**.

## Quick Start

The simplest possible drop-in. With `OPENAI_API_KEY` set in your environment:

```python
# Before
from openai import OpenAI
client = OpenAI()

# After (drop-in replacement)
from tokenopt import OpenAI
client = OpenAI()

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Long prompt..."}],
)

# Check savings
print(client.get_metrics_summary())
```

Run it end-to-end: `python examples/quickstart.py`.

## Examples by provider

### OpenAI

```python
from tokenopt import OpenAI, TokenOptConfig

config = TokenOptConfig(
    compression_ratio=0.5,
    cache_enabled=True,      # in-memory semantic cache
    enable_routing=True,     # route simple queries to cheaper models
)
client = OpenAI(config=config)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Explain semantic caching in one sentence."}],
)
print(response.choices[0].message.content)
```

Full script: `examples/openai_basic.py` — sends the same long prompt through
a plain client vs a compressed client (~50% fewer tokens), then repeats the
call to show the cache miss → hit behavior.

### Anthropic

```python
from tokenopt import Anthropic

client = Anthropic()  # reads ANTHROPIC_API_KEY

response = client.messages.create(
    model="claude-3-5-haiku",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Write a one-line haiku about caching."}],
)
print("".join(block.text for block in response.content))
```

Full script: `examples/anthropic_basic.py` — a 5-turn conversation that
exceeds the summarization threshold; older turns are condensed into a
summary instead of being sent verbatim.

### Local models (Ollama, vLLM, llama.cpp, LM Studio)

```python
from tokenopt import LocalClient

# Ollama (default URL uses the native `ollama` package; needs `[local]` extra)
client = LocalClient(model="llama3.1")

# Any OpenAI-compatible server: vLLM, llama.cpp, LM Studio (no extra needed)
client = LocalClient(model="qwen2.5", base_url="http://localhost:8000/v1")

response = client.chat.completions.create(
    messages=[{"role": "user", "content": "Hello! Who are you?"}],
)
print(response.choices[0].message.content)
```

Full script: `examples/local_basic.py` — a multi-paragraph code-review prompt
compressed before the local model sees it, then a repeat request served from
the cache (no inference call). Cloud routing rules are auto-skipped for
local backends.

### One client, any provider (factory)

```python
from tokenopt import create_client, create_client_from_model

# Auto-detect provider from the model name
client = create_client_from_model("claude-3-5-haiku", api_key=...)
client = create_client_from_model("llama3.1", base_url="http://localhost:11434")

# Explicit provider + endpoint
local = create_client(
    provider="local",
    model="qwen2.5",
    base_url="http://localhost:8000/v1",
)
```

## Configuration

`TokenOptConfig` controls every optimization stage:

```python
from tokenopt import OpenAI, RoutingRule, TokenOptConfig

config = TokenOptConfig(
    compression_ratio=0.5,          # target prompt size reduction
    cache_enabled=True,
    cache_ttl=3600,
    enable_routing=True,
    routing_rules=[                 # custom routing (checked by priority)
        RoutingRule(
            name="math_tasks",
            condition=lambda q, m: "equation" in q.lower(),
            model="o1-mini",
            priority=10,
        ),
    ],
    enable_summarization=True,
    summarization_threshold=8000,   # token count that triggers summarization
    rag_max_chunks=5,
    fewshot_max_examples=3,
    metrics_callback=my_callback,   # per-request hook (see observability)
)
client = OpenAI(config=config)
```

Run it: `examples/pipeline_config.py` — four prompts, four routing decisions
(custom rule → `o1-mini`, complexity fallback → `gpt-4o`/`gpt-4o-mini`), each
with its `routing_reason`, plus routing OFF vs ON; and
`examples/metrics_observability.py` — every metric annotated, the latency
split explained, and the callback hook for your own monitoring.

## Supported providers & features

| Provider | Models | Backend |
|----------|--------|---------|
| OpenAI | `gpt-*`, `o1-*`, `o3-*` | official `openai` SDK |
| Anthropic | `claude-*` | official `anthropic` SDK |
| Local | Ollama (`http://localhost:11434`), vLLM, llama.cpp, LM Studio (`/v1`) | `ollama` package or `openai` SDK |

Features (all configurable via `TokenOptConfig`): model routing, prompt
compression, conversation summarization, semantic caching (in-memory or
Redis), RAG chunk optimization, few-shot selection, metrics + cost
estimation.

## Project structure

```
tokenopt/
├── clients/          # OpenAI, Anthropic, LocalClient, base drop-in wrappers
├── pipeline/         # routing, compression, summarization, cache, RAG, few-shot
├── observability/    # metrics collection, cost estimation, structured logging
├── utils/            # token counting, truncation, embeddings
├── config.py         # TokenOptConfig, RoutingRule, default config
└── factory.py        # create_client / create_client_from_model / detect_provider
examples/             # runnable scripts for every primary workflow
tests/                # unit + integration suite (offline, deterministic)
```

See `.ai/ARCHITECTURE.md` for a full architecture overview.

## Troubleshooting / FAQ

**`ModuleNotFoundError: No module named 'ollama'`**
The Ollama backend needs the `ollama` package: `pip install -e ".[local]"`.
Or point `base_url` at an OpenAI-compatible server (vLLM, llama.cpp, LM
Studio) — no extra needed.

**`AuthenticationError` / `401` on OpenAI or Anthropic**
Set the API key as an environment variable (`OPENAI_API_KEY` /
`ANTHROPIC_API_KEY`) or pass `api_key=` to the client. The SDK itself never
stores or logs keys.

**My prompts aren't being compressed / saved tokens**
- Optimization is **fails open** and conservative by default: on short
  prompts the compressor only removes fillers/whitespace (truncation kicks
  in above the `compression_ratio` token budget), so savings are small —
  there is simply little to save.
- Routing only applies when `enable_routing=True` and (for Anthropic/Local)
  custom rules targeting that provider's models exist.
- Summarization only triggers on multi-turn conversations above
  `summarization_threshold` tokens.
- Verify what happened: `client.get_metrics_summary()` shows
  `optimization_usage` and `avg_token_reduction_pct` per request.

**Second identical call didn't hit the cache**
Cache keys include the model and conversation; different `model` values are
separate entries. In-memory cache lives on the client instance — create the
client once and reuse it.

**I want to disable all optimization**
`TokenOptConfig(enable_compression=False, cache_enabled=False,
enable_routing=False, enable_summarization=False, observability_enabled=False)`
— the SDK then behaves as a thin passthrough.

**Does TokenOpt work with streaming?**
Local clients accept `stream=True` passthrough; the base OpenAI/Anthropic
flows are non-streaming in v0.1.0 (async/streaming is on the roadmap).

**Do I need `sentence-transformers` for caching?**
No — the in-memory cache falls back to deterministic hashing when the
`sentence-transformers` extra isn't installed. Install `[semantic]` for
near-duplicate (semantic) cache hits.

**Python version support?**
Python ≥ 3.10; CI tests 3.10, 3.11, 3.12.

## Development

```bash
make dev                # or: pip install -e ".[dev]"
make test               # pytest tests/
make lint               # ruff check tokenopt tests
make typecheck          # mypy tokenopt
make build              # python -m build
make audit              # pip-audit --path . (security scan)
```

See `CONTRIBUTING.md` for the Definition of Done gates, CI pipeline, and
branch protection recommendations.

## Continuous Integration

Every push to `main` and every pull request runs the CI pipeline
(`.github/workflows/ci.yml`) — the project's single source of truth for
release readiness. It executes the DoD gates:

1. **Lint** — `ruff check tokenopt tests` + `mypy tokenopt`
2. **Test** — `pytest tests/` on Python 3.10, 3.11, and 3.12, with the
   **≥80% coverage gate** enforced by pytest itself
3. **Package** — `python -m build` (sdist + wheel) plus a fresh-venv
   install and `import tokenopt` smoke test
4. **Security** — `pip-audit` (dependency vulnerabilities) + `gitleaks`
   (secret scan of full git history) — see `SECURITY.md`

## Status

Pre-1.0 (**v0.1.0**): the public API is stabilizing but may still evolve.
Optimization is best-effort and always fails open — an optimization error
never blocks the underlying request. Feedback and contributions welcome via
GitHub issues.

## License

[MIT](LICENSE)
