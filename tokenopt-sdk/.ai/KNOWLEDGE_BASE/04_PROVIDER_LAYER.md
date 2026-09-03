# 04 — Provider Layer

*Part of the [Architecture Knowledge Base](README.md).*

## Abstraction model

`BaseOptimizedClient` (`tokenopt/clients/base.py`) is a template-method
abstraction: the shared request flow (`chat_completion` → pipeline → metrics)
is implemented once; providers implement exactly four seams:

| Seam | Contract |
|------|----------|
| `_create_client()` | Build the underlying SDK client (`api_key`, `base_url`, extra kwargs) |
| `_call_api(messages, model, **kwargs)` | Perform the API call; return the provider response |
| `_extract_response_content(response)` | Return the text content for metrics/logging |
| `_extract_usage(response)` | Map provider usage to `{prompt_tokens, completion_tokens, total_tokens}` |

Optional seam:

- `_build_pipeline(routing_rule_filter=None)` — only providers whose
  endpoints cannot serve models matched by generic rules override/limit it.

Shared behavior in the base:

- `chat_completion` owns the full request lifecycle
  ([02 — Request Lifecycle](02_REQUEST_LIFECYCLE.md)).
- `__getattr__` delegates unknown attributes to the underlying client —
  provider-native calls keep working even when not explicitly wrapped.
- The drop-in surface (`chat.completions` / `messages`) is one shared
  `_CompatShim` (`clients/_compat.py`, M13 R4).

## Provider responsibilities

Each provider must guarantee:

1. **Native surface fidelity** — the drop-in shape the user expects
   (`chat.completions.create` for OpenAI/local, `messages.create` for
   Anthropic).
2. **Router compatibility** — never route to a model the endpoint cannot
   serve (`Decisions 8, 13`; enforced via `routing_rule_filter`).
3. **Normalized response** — content and usage extractable by the two
   `_extract_*` seams (local additionally normalizes the whole response).
4. **Fail-open posture** — missing optional dependencies produce clear,
   actionable errors at client construction (e.g. Ollama without the
   `ollama` package, `Decision 16`), not mid-request crashes.

## OpenAI

- Wraps `openai.OpenAI` (`_create_client`), calls
  `chat.completions.create`, extracts `choices[0].message.content` and
  OpenAI-shaped `usage`.
- Usage mapping shared with the local provider via
  `_extract_openai_shape_usage` (M13 R3).
- Full default pipeline (all six stages, default rules) — the reference
  provider.

## Anthropic

- Wraps `anthropic.Anthropic`; calls `messages.create`.
- **Message translation**: `system` role content is extracted into the
  `system=` parameter; `user`/`assistant` messages are passed through;
  `max_tokens` defaults to 4096 and is filtered from passthrough kwargs.
- **Content extraction**: joins text blocks (`response.content`).
- **Usage mapping**: `input_tokens` → `prompt_tokens`,
  `output_tokens` → `completion_tokens`.
- **Router scoping**: the default router targets OpenAI models; the
  Anthropic adapter keeps only custom rules whose model contains `claude`
  (`Decision 13`). With no such rules, the router is omitted.

## Local provider (`LocalClient`)

One class serves every local backend by **auto-detection**
(`_detect_backend`):

| Backend | Detection | Call |
|---------|-----------|------|
| Ollama (native) | base URL contains `11434` or `ollama` | `ollama.Client(...).chat(...)` (needs `tokenopt[local]`; clear error otherwise, `Decision 16`) |
| OpenAI-compatible (vLLM, llama.cpp, LM Studio) | anything else | `openai.OpenAI(...)` + `chat.completions.create` |

Other responsibilities:

- **Default local model**: `model=` defaults to `llama3.1`
  (`default_local_model`) and flows through `chat_completion` when the
  caller omits it.
- **Router scoping**: only custom rules targeting non-cloud models
  (`gpt-*`, `o1-*`, `o3-*`, `claude`) are kept; the router is omitted when
  none remain (`Decision 8`).
- **Explicitness pass-through**: `chat_completion(model=...)` on the local
  client derives `model_explicit` the same way the base does, so the
  routing contract holds (`Decision 24`).

### Response-normalization contract (LocalClient → OpenAI shape)

Ollama responses are converted to the OpenAI chat-completion shape
(`Decision 7`) so the pipeline, cache, and metrics are backend-agnostic:

```
SimpleNamespace(
    model=...,                                    # Ollama model name
    choices=[SimpleNamespace(
        message=SimpleNamespace(content=...),     # message.content
        finish_reason="stop",
    )],
    usage=SimpleNamespace(                        # prompt_eval_count / eval_count
        prompt_tokens=...,
        completion_tokens=...,
        total_tokens=...,
    ),
)
```

Properties of the contract:

- Content is taken from `message.content`; usage from
  `prompt_eval_count`/`eval_count` (defaulting to 0).
- After normalization the local provider reuses the OpenAI-shaped usage
  extraction (M13 R3) and the OpenAI-shaped content extraction.
- The contract is deliberately **not** a schema-validated model today;
  formal enforcement is tracked as ADB-13.

## Factory

`tokenopt/factory.py` is the single entry point for provider-agnostic
construction:

- `detect_provider(model, base_url)` — base URL containing `11434` → local;
  model prefixes `gpt-`/`o1-`/`o3-`/`gpt`/`text-` → openai; `claude` →
  anthropic; else local (`Decision 9`).
- `create_client(provider="auto", ...)` — explicit provider wins over
  detection; model becomes `default_model` when no config is given.
- `create_client_from_model(model)` — convenience auto-detect wrapper.
