# TokenOpt SDK - Session Backup / Handoff Document

## Project Overview
Building a **Python SDK for token and prompt optimization** that wraps OpenAI/Anthropic clients as drop-in replacements. Users change `from openai import OpenAI` to `from tokenopt import OpenAI` and get automatic optimization.

**Goals:** Cost reduction, context window management, latency optimization, quality preservation
**Target:** Personal/small team use, multi-model routing (Anthropic, OpenAI, local)
**Interface:** SDK/Library (drop-in wrapper pattern)

---

## Current Implementation Status

### ✅ Completed (Phase 1: Core Infrastructure)

#### Project Setup
- `pyproject.toml` - Dependencies, optional extras (cache, semantic, compression, local, dev)
- Directory structure: `tokenopt/{clients,pipeline,observability,utils,config}`

#### Core Modules

| File | Purpose | Key Components |
|------|---------|----------------|
| `tokenopt/config.py` | Configuration dataclass | `TokenOptConfig`, `RoutingRule`, `get_default_config()` |
| `tokenopt/utils/token_counter.py` | Tiktoken-based counting | `count_tokens()`, `count_message_tokens()`, `truncate_to_tokens()` |
| `tokenopt/utils/embeddings.py` | Embedding providers | `EmbeddingProvider` (sentence-transformers), `SimpleEmbeddingProvider` (fallback), `get_embedding_provider()` |
| `tokenopt/pipeline/base.py` | Pipeline framework | `OptimizationContext`, `PipelineStage`, `OptimizationPipeline` |
| `tokenopt/pipeline/compressor.py` | Prompt compression | `CompressorStage` (LLMLingua + heuristic fallback), `ContextSummarizerStage` |
| `tokenopt/pipeline/cache.py` | Semantic caching | `CacheStage` with in-memory LRU + optional Redis, similarity search |
| `tokenopt/pipeline/router.py` | Model routing | `RouterStage` with rule-based + complexity-based routing |
| `tokenopt/pipeline/rag_optimizer.py` | RAG/few-shot optimization | `RAGOptimizerStage`, `FewShotSelectorStage` |
| `tokenopt/observability/metrics.py` | Metrics collection | `MetricsCollector`, `RequestMetrics`, `estimate_cost()` |
| `tokenopt/observability/logger.py` | Structured logging | `StructuredLogger`, `JsonFormatter` |
| `tokenopt/clients/base.py` | Base client wrapper | `BaseOptimizedClient` with pipeline integration, metrics recording |
| `tokenopt/clients/openai_client.py` | OpenAI wrapper | `OpenAI` class - drop-in for `openai.OpenAI` |
| `tokenopt/clients/anthropic_client.py` | Anthropic wrapper | `Anthropic` class - drop-in for `anthropic.Anthropic` |
| `tokenopt/clients/local_client.py` | Local wrapper | `LocalClient` - Ollama/vLLM/llama.cpp, backend auto-detect from base_url |
| `tokenopt/clients/__init__.py` | Client exports | `BaseOptimizedClient`, `OpenAI`, `Anthropic`, `LocalClient` |
| `tokenopt/factory.py` | Client factory | `create_client()`, `create_client_from_model()`, `detect_provider()` |
| `tokenopt/__init__.py` | Package exports | `TokenOptConfig`, `OpenAI`, `Anthropic`, `LocalClient`, factory, metrics |
| `tests/` | Unit tests | 23 tests: imports, local client, factory |

---

## 📋 Remaining Work (Phase 2+)

### Immediate Next Steps
1. ~~**Local client**~~ ✅ - `tokenopt/clients/local_client.py` (Ollama/vLLM/llama.cpp, auto-detect backend)
2. ~~**Package init**~~ ✅ - `tokenopt/__init__.py` with exports, `clients/__init__.py`
3. ~~**Client factory**~~ ✅ - `tokenopt/factory.py`: `create_client()`, `create_client_from_model()` (auto-detect via model name/base_url)
4. **Tests** - ✅ 23 unit tests (imports, local client, factory). TODO: pipeline stage unit tests (compressor/cache/router/RAG), integration tests
5. **Documentation** - README, usage examples

### Pipeline Stages to Enhance
- **Compressor**: Integrate actual LLMLingua when available, improve heuristic rules
- **Cache**: Add persistence, better eviction policies
- **Router**: Add cost/latency tracking per model, dynamic routing
- **Summarizer**: Plug in actual summarization model (configurable)
- **RAG Optimizer**: Support more chunk formats, metadata filtering
- **FewShot**: Diversity selection improvement, example management

### Observability
- Prometheus exporter option
- Dashboard/visualization helpers
- Cost tracking per project/model

### Advanced Features (Post-v1)
- Prompt versioning/registry
- A/B testing framework
- Team config sharing
- Web UI for experimentation

---

## Key Design Decisions

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Language | Python | ML ecosystem, SDK compatibility |
| Integration | Drop-in wrapper | Zero code changes for users |
| Cache | In-memory + optional Redis | Simple for personal use, scalable |
| Compression | Heuristic + optional ML | No heavy deps by default; pluggable |
| Routing | Rule-based + complexity scoring | Transparent, configurable |
| Observability | Built-in + callbacks | No external deps required |

---

## Usage Example (When Complete)

```python
# Before
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Long prompt..."}]
)

# After (drop-in replacement)
from tokenopt import OpenAI
client = OpenAI()  # Same API, auto-optimization
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Long prompt..."}]
)

# Check savings
print(client.get_metrics_summary())
# {'total_requests': 1, 'cache_hit_rate': 0.0, 'avg_token_reduction_pct': 42.3, ...}
```

---

## Configuration Example

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

---

## Dependencies

**Required:** `openai`, `anthropic`, `tiktoken`, `pydantic`, `pydantic-settings`

**Optional extras:**
- `pip install tokenopt[cache]` - Redis support
- `pip install tokenopt[semantic]` - sentence-transformers for semantic cache
- `pip install tokenopt[compression]` - LLMLingua for ML compression
- `pip install tokenopt[local]` - Ollama support
- `pip install tokenopt[all]` - Everything

---

## File Tree
```
tokenopt/
├── __init__.py              # ✅ Exports: config, clients, factory, metrics, utils
├── config.py                # ✅ TokenOptConfig, RoutingRule
├── factory.py               # ✅ create_client, create_client_from_model, detect_provider
├── clients/
│   ├── __init__.py          # ✅ Exports BaseOptimizedClient, OpenAI, Anthropic, LocalClient
│   ├── base.py              # ✅ BaseOptimizedClient
│   ├── openai_client.py     # ✅ OpenAI wrapper
│   ├── anthropic_client.py  # ✅ Anthropic wrapper
│   └── local_client.py      # ✅ LocalClient (Ollama/vLLM/llama.cpp)
├── pipeline/
│   ├── __init__.py          # ✅ Exports all stages
│   ├── base.py              # ✅ Pipeline framework
│   ├── compressor.py        # ✅ Compression + Summarization
│   ├── cache.py             # ✅ Semantic cache
│   ├── router.py            # ✅ Model routing
│   └── rag_optimizer.py     # ✅ RAG + Few-shot
├── observability/
│   ├── __init__.py          # ✅ Exports
│   ├── metrics.py           # ✅ MetricsCollector, cost estimation
│   └── logger.py            # ✅ Structured JSON logging
└── utils/
    ├── __init__.py          # ✅ Exports
    ├── token_counter.py     # ✅ Tiktoken utilities
    └── embeddings.py        # ✅ Embedding providers
tests/
├── test_imports.py          # ✅ Drop-in API surface
├── test_local_client.py     # ✅ LocalClient pipeline/cache/metrics (stubbed)
└── test_factory.py          # ✅ Factory + provider auto-detection
```

---

## How to Resume in New Chat

1. **Read this file** for context
2. **Explore the codebase**: `ls -la C:\Projects\New Project\tokenopt\`
3. **Next task**: Pipeline stage unit tests + README docs (per `pyproject.toml` `readme = "README.md"` which doesn't exist yet)
4. **Run tests**: `pytest tests/`
5. **Verify**: Import and test drop-in replacement works

```python
# Quick verification
from tokenopt import OpenAI, LocalClient, create_client, create_client_from_model
client = OpenAI(api_key="test")  # Won't call API without key
local = create_client(model="llama3.1", base_url="http://localhost:11434", api_key="test")
print("Import successful")
```

---

## Notes for Continuation

- All pipeline stages are modular and can be enabled/disabled via config
- Base client handles metrics recording automatically
- Cache stage stores responses after successful API calls
- Router runs FIRST in pipeline (determines model before compression)
- LocalClient drops the router by default (cloud rules would break local servers); custom routing rules targeting local models are honored
- Summarizer triggers only when token count exceeds threshold
- RAG optimizer looks for "context:" or "retrieved:" patterns in messages
- FewShot selector needs examples provided at initialization
- LocalClient normalizes Ollama responses to OpenAI chat format (`choices[0].message.content`, `usage`) so cache/metrics work unchanged
- `create_client(provider="auto")` detects provider from model prefix (gpt-/o1-/o3- → openai, claude → anthropic, else local) or base_url containing `11434`

**No breaking changes expected** - the wrapper pattern maintains full API compatibility.