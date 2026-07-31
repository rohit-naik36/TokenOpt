# TokenOpt SDK

Token and prompt optimization for LLM clients — a **drop-in replacement** for
OpenAI/Anthropic (plus local models via Ollama/vLLM/llama.cpp) that
automatically reduces token usage and cost.

- **Cost reduction** — prompt compression, summarization, model routing
- **Context management** — semantic caching, RAG chunk optimization
- **Latency** — cheap-model routing for simple queries, cache hits avoid API calls
- **Quality preservation** — quality-aware routing and similarity-based few-shot selection

## Install

```bash
pip install -e .            # core (openai, anthropic, tiktoken, pydantic, numpy)
pip install -e ".[all]"     # everything (Redis, sentence-transformers, LLMLingua, ollama)
pip install -e ".[local]"   # just local model support
```

## Quick start

```python
# Before
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Long prompt..."}],
)

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

## Multi-model / local models

```python
from tokenopt import create_client, create_client_from_model

# Auto-detect provider from model name
client = create_client_from_model("claude-3-5-haiku", api_key=...)
client = create_client_from_model("llama3.1", base_url="http://localhost:11434")

# Explicit provider + endpoint
local = create_client(
    provider="local",
    model="qwen2.5",
    base_url="http://localhost:8000/v1",  # vLLM / llama.cpp / LM Studio
)
response = local.chat.completions.create(
    messages=[{"role": "user", "content": "Hello"}]
)
```

`LocalClient` auto-detects the backend: the default Ollama URL
(`http://localhost:11434`) uses the native `ollama` package; any other
`base_url` is treated as an OpenAI-compatible server.

## Configuration

```python
from tokenopt import OpenAI, TokenOptConfig

config = TokenOptConfig(
    compression_ratio=0.5,
    cache_enabled=True,
    cache_ttl=3600,
    enable_routing=True,
    enable_summarization=True,
    summarization_threshold=8000,
    rag_max_chunks=5,
    fewshot_max_examples=3,
)
client = OpenAI(config=config)
```

## Development

```bash
pip install -e ".[dev]"
pytest tests/
ruff check tokenopt tests
mypy tokenopt
python -m build
```

## Definition of Done

Every milestone and feature must satisfy the verification gates in
`.ai/DOD.md` before it is committed.

## Project layout

See `.ai/ARCHITECTURE.md` for a full architecture overview and
`.ai/ROADMAP.md` for the development plan.

## License

TBD
