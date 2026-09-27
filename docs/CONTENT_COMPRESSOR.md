# ContentCompressor — How to Use

The `ContentCompressor` is a TokenOpt pipeline stage that compresses tool
results and large assistant messages before they are sent to the model. It
targets the content type the default transformer misses — JSON arrays returned
by tool calls, retrieved context, and verbose assistant turns — which is where
the real token spend is in agentic workloads.

---

## Quick start

```python
from tokenopt import OpenAI
from tokenopt.config import TokenOptConfig

client = OpenAI(
    config=TokenOptConfig(content_compression_enabled=True)
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Summarise the quarterly report."}],
)

print(response.choices[0].message.content)
print(client.get_metrics_summary())
```

`get_metrics_summary()` will include:

| Key | What it tells you |
|-----|-------------------|
| `content_compressor_tokens_saved` | Input tokens saved this call |
| `content_compressor_messages_compressed` | Number of messages that were compressed |
| `content_compressor_backend` | `"headroom"` (Rust, best) or `"fallback"` (pure-Python) |

---

## Installation

### Minimal (pure-Python fallback, no extra dependencies)

```bash
pip install tokenopt
```

The fallback handles JSON arrays: it keeps the first 30 % and last 15 % of
array items and deduplicates identical rows. Everything else passes through
unchanged.

### Full (headroom Rust backend, 60–95 % reduction on JSON arrays)

```bash
pip install tokenopt headroom
```

With headroom installed, the stage automatically uses the Rust-backed
`SmartCrusher` for JSON arrays and `Kompress` (ModernBERT ML) for prose. No
code change required — the backend is detected at import time.

---

## Run locally (step by step)

### 1. Clone and install

```bash
git clone https://github.com/rohit-naik36/TokenOpt.git
cd TokenOpt
pip install -e tokenopt-optimizer/   # standalone optimizer engine
pip install -e .                     # main SDK
pip install headroom                 # optional but recommended
```

### 2. Verify the stage is available

```python
from tokenopt.pipeline import ContentCompressorStage
print(ContentCompressorStage.name)   # → "content_compressor"
```

### 3. Run the optimizer standalone (no LLM call)

Use this to measure token savings on a captured runtime trace without hitting
any API:

```python
import json
from tokenopt_optimizer import CanonicalOptimizer, get_prototype_config
from tokenopt.config import TokenOptConfig

# Load a real runtime trace (the full messages array from one LLM call)
with open("runtime_trace.json") as f:
    messages = json.load(f)

config = TokenOptConfig(content_compression_enabled=True)
optimizer = CanonicalOptimizer(config)
result = optimizer.optimize(messages, model="gpt-4o")

print(f"Before : {result.original_token_count:,} tokens")
print(f"After  : {result.optimized_token_count:,} tokens")
print(f"Saved  : {result.tokens_saved:,} ({result.compression_ratio:.1%})")
print(f"Backend: {result.metrics.get('content_compressor_backend')}")
```

Save a runtime trace by adding one line before any LLM call in your codebase:

```python
import json, pathlib
pathlib.Path("runtime_trace.json").write_text(json.dumps(messages, indent=2))
```

### 4. Drop-in for Anthropic

```python
from tokenopt import Anthropic
from tokenopt.config import TokenOptConfig

client = Anthropic(
    config=TokenOptConfig(content_compression_enabled=True)
)

response = client.messages.create(
    model="claude-opus-5-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "..."}],
)
print(client.get_metrics_summary())
```

### 5. Drop-in for local models (Ollama / vLLM / llama.cpp)

```python
from tokenopt import LocalClient
from tokenopt.config import TokenOptConfig

client = LocalClient(
    base_url="http://localhost:11434/v1",
    config=TokenOptConfig(content_compression_enabled=True),
)

response = client.chat.completions.create(
    model="llama3",
    messages=[{"role": "user", "content": "..."}],
)
print(client.get_metrics_summary())
```

---

## Run the test suite

```bash
# New ContentCompressor tests (21 tests)
cd TokenOpt
python -m pytest tokenopt-optimizer/tests/test_content_compressor.py tests/test_content_compressor.py -v

# Full suite
python -m pytest tests/ -v
```

---

## Configuration reference

```python
from tokenopt.config import TokenOptConfig

config = TokenOptConfig(
    content_compression_enabled=True,   # enable the stage (default: False)
    # all other existing TokenOptConfig fields continue to work unchanged
)
```

The stage is **off by default** so existing integrations are unaffected. Set
`content_compression_enabled=True` to activate it.

---

## How it works

```
messages
  │
  ▼
AnalyzerStage          ← classifies messages, counts tokens
  │
  ▼
ContentCompressorStage ← NEW: compresses tool results + large assistant msgs
  │  • role="tool" messages → always compressed
  │  • role="assistant" messages ≥ 500 tokens → compressed
  │  • everything else → passed through unchanged
  │  • headroom backend (Rust): JSON arrays, prose, code, logs, search results
  │  • fallback (pure-Python): JSON array sampling only
  │  • fail-open: any error → original message unchanged
  ▼
RouterStage
  │
  ▼
TransformerStage       ← existing filler/whitespace/duplicate-sentence removal
  │
  ▼
ValidatorStage         ← fidelity check; rolls back if quality drops
```

The two backends:

| Backend | Triggered when | What it compresses |
|---------|----------------|--------------------|
| `headroom` (Rust) | `pip install headroom` succeeds | JSON arrays (SmartCrusher), prose (Kompress ML), logs, search results, source code |
| `fallback` (pure-Python) | headroom not installed | JSON arrays only — keeps first 30 % + last 15 % of items, deduplicates identical rows |

---

## What to expect

| Prompt type | Expected saving |
|-------------|-----------------|
| Agent definitions / static config (dense directives) | ~1 % (same as before — little redundancy) |
| Tool results containing JSON arrays | 30–95 % (depends on array size and duplication) |
| Retrieved RAG context (large text blobs) | 20–60 % with headroom ML backend |
| Mixed runtime trace (system + tool results + history) | 15–50 % typical |

The 0.93 % result from the static AAVA agent-definition benchmark reflects the
first row above. Real agentic runtime traces that include tool call results are
the target workload for this stage.
