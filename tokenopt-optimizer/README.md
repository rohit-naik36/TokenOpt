# TokenOpt Optimizer

Standalone, embeddable prompt-optimization engine with fidelity validation.

This package extracts the optimization core into a dependency-light library so
it can be dropped into any host application (a FastAPI proxy, an LLM gateway, a
batch job, or another vendor's platform) without inheriting the full service
stack.

## Features

- Deterministic, dependency-free compression (filler removal, connector
  simplification, whitespace collapse).
- Optional headroom integration that **fails open** when unavailable.
- Pluggable async fidelity validator with a fails-open default, including
  optional response-level fidelity checking.
- Pluggable token counter (falls back to a word-based heuristic).
- Framework-agnostic message input (plain dicts or `Message` dataclasses).
- Works with either sync or async cache backends.
- In-process LRU cache with optional TTL expiration.
- Batch optimization via `optimize_batch()`.
- MIT licensed.

## Quick start

```python
import asyncio
from tokenopt_optimizer import Message, OptimizerConfig, PromptOptimizer


async def main():
    optimizer = PromptOptimizer(config=OptimizerConfig(enable_headroom=False))
    result = await optimizer.optimize(
        [Message(role="user", content="Please basically explain it to us in order to help")]
    )
    print(result["optimized_prompt"])
    print(result["optimized_tokens"], "tokens")
    print("fidelity passed:", result["fidelity_passed"])


asyncio.run(main())
```

## Public API

| Symbol | Purpose |
|---|---|
| `PromptOptimizer` | Orchestrates compression + fidelity validation. |
| `OptimizerConfig` | Tuning knobs (headroom, caching, tokenizer, message limits). |
| `SemanticCompressorV2` | Deterministic compression engine. |
| `Message` | Framework-agnostic chat message (`role`/`content`/`name`). |
| `FidelityScore` | Result of a fidelity check. |
| `DegradedFidelityValidator` | Fails-open validator (default backend). |
| `FidelityValidator` / `CacheBackend` | Pluggable protocols. |

## Dependency injection

The optimizer has **no hard runtime dependencies** (standard library only) and
reads nothing from globals. Everything is injected:

- `config`: an `OptimizerConfig`.
- `validator`: any object exposing `async validate(original_prompt,
  optimized_prompt, ...) -> FidelityScore` and `get_stats()`. Defaults to a
  fails-open degraded validator.
- `cache`: any object exposing `get(prefix, key)` / `set(prefix, key, value,
  ttl=None)`, sync or async. Defaults to a small in-process LRU cache.
- `compressor`: optional compressor; defaults to `SemanticCompressorV2`.

```python
class MyValidator:
    async def validate(self, original_prompt, optimized_prompt, **kwargs):
        # ... production fidelity check ...
        return FidelityScore(
            overall=0.99,
            semantic_similarity=0.99,
            structural_similarity=1.0,
            llm_judge_score=None,
            passed=True,
            details={"engine": "mine"},
        )

    def get_stats(self):
        return {}


optimizer = PromptOptimizer(config=..., validator=MyValidator(), cache=my_redis_cache)
```

## Configuration options

`OptimizerConfig` is a frozen dataclass supporting:

- `enable_headroom` / `headroom_target_ratio` / `headroom_min_tokens` /
  `headroom_llm_model` — headroom pipeline tuning.
- `cache_enabled` / `cache_ttl` — enable caching and set a default TTL (seconds).
- `tokenizer` — a `Callable[[str], int]` used to count tokens. Defaults to a
  word-count heuristic.
- `max_messages` — optional cap on the number of messages optimized per call.

## Response-level fidelity

Pass optional `baseline_response` / `optimized_response` strings to `optimize()`
(or the corresponding response lists to `optimize_batch()`) to enable
response-level fidelity checks:

```python
result = await optimizer.optimize(
    messages,
    baseline_response="long answer...",
    optimized_response="short answer...",
)
```

## Batch optimization

```python
results = await optimizer.optimize_batch(
    [[Message(role="user", content="q1")], [Message(role="user", content="q2")]],
)
```

Concurrent optimization with optional per-prompt response fidelity inputs.

## Optional dependencies

- `tokenopt-optimizer[headroom]` enables the headroom compression pipeline.
  Without it, compression falls back to the deterministic engine and never
  raises.

## License

MIT — see [LICENSE](LICENSE).
