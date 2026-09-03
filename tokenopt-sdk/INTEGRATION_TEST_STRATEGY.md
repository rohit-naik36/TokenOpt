# INTEGRATION_TEST_STRATEGY.md

> Milestone M4 deliverable — Integration Tests & Coverage Gate.
> Companion to `.ai/STANDARDS/testing-standard.md` (unit-level rules).

## 1. Purpose

Integration tests prove that the **whole optimized client flow works together**:

```
user call → optimization pipeline (route/compress/summarize/cache/RAG/few-shot)
         → provider adapter (SDK call) → cache store → metrics → response
```

Unit tests validate individual stages in isolation; integration tests validate
that they compose correctly through the real `BaseOptimizedClient.chat_completion`
flow and the real provider SDKs (OpenAI / Anthropic / local adapters).

## 2. Definition of an integration test

A test belongs in `tests/integration/` when it exercises **at least two layers**
of the stack through a public entry point (`client.chat.completions.create`,
`client.messages.create`, `create_client(...)`), e.g.:

- pipeline → provider adapter (request body assertions)
- provider adapter → cache (cache-hit short-circuit, hit-rate metrics)
- provider adapter → metrics/observability (error recording, callbacks)
- factory → client → provider adapter (kwargs forwarding)

Tests that exercise a single stage or a pure function belong in `tests/`
(unit tier).

## 3. Offline execution policy

**Integration tests never touch the network. Period.** All provider traffic is
intercepted at the HTTP layer:

- Each test injects `httpx.MockTransport(handler)` into the provider SDK via the
  `http_client=` keyword (forwarded through `extra_kwargs` to the underlying
  `openai.OpenAI` / `anthropic.Anthropic` client).
- The handler is an in-process callable that decodes the request JSON and returns
  a provider-shaped JSON response (OpenAI chat.completion / Anthropic message
  payloads).
- Handlers **record every request body** into a per-test list so tests can assert
  what was actually sent (model chosen by routing, optimized message content,
  request counts for cache behavior).
- Error paths use handlers returning 500 responses; the SDKs raise
  `openai.APIStatusError` / `anthropic.APIStatusError`, which the client records
  in metrics before re-raising.

This approach requires **zero new dependencies** (`httpx` is already a transitive
dependency of the openai/anthropic SDKs). The M4 dev-dependency budget approved
in the roadmap was not needed and was deliberately left unspent to keep the
dependency surface minimal.

## 4. What is covered

| Dimension | Coverage |
|---|---|
| E2E pipeline | full optimize → call → cache → metrics flow via public API |
| Provider adapters | OpenAI chat.completions, Anthropic messages (system split, max_tokens default), LocalClient (OpenAI-compatible backend + Ollama backend) |
| Config handling | custom routing rules, disabled compression, metrics callback |
| Cache interaction | identical second call short-circuits provider (1 request total), cache_hit_rate in summary |
| Error paths | provider 5xx recorded in metrics + re-raised; pipeline stage failure fails open |
| Factory | `create_client(...)` forwards `http_client` and builds working clients |

## 5. Determinism rules

- Fixed mock payloads only; no live data, no `sleep`, no timing assertions
  (latency is measured but never asserted).
- Every test builds its own client + transport (fresh cache per test; no shared
  state, no test-order dependence).
- No API keys are ever required — `"test-key"` placeholders only.
- Tests are fully synchronous and CI-friendly (pytest only, no external services).

## 6. Coverage gate

- `[tool.coverage] fail_under = 80` in `pyproject.toml`.
- Enforced on every `pytest` run via `addopts = --cov=tokenopt`.
- `pytest --cov` (the DOD gate) must report overall line coverage ≥ 80% for the
  `tokenopt` package. Gate failures are merge blockers.

## 7. Test lifecycle

- Added/updated alongside any change to clients, pipeline, cache, or metrics.
- A genuine integration defect found by this suite is a production bug:
  fix it (minimally), add a regression test, and document in SESSION_LOG.
- Never weaken assertions to make a red suite green — the suite is the contract.
