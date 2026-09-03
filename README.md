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
- Pluggable async fidelity validator with a fails-open default.
- Framework-agnostic message input (plain dicts or `Message` dataclasses).
- Works with either sync or async cache backends.

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
| `OptimizerConfig` | Tuning knobs (headroom on/off, ratio, min tokens, caching). |
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
  ttl=None)`, sync or async. Defaults to a small in-process cache.

```python
class MyValidator:
    async def validate(self, original_prompt, optimized_prompt, **kwargs):
        # ... production fidelity check ...
        return FidelityScore(overall=0.99, semantic_similarity=0.99,
                             structural_similarity=1.0, llm_judge_score=None,
                             passed=True, details={"engine": "mine"})

    def get_stats(self):
        return {}

optimizer = PromptOptimizer(config=..., validator=MyValidator(), cache=my_redis_cache)
```

## Optional dependencies

- `tokenopt-optimizer[headroom]` enables the headroom compression pipeline.
  Without it, compression falls back to the deterministic engine and never
  raises.
