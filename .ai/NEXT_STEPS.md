# Next Steps

_Last updated: 2026-08-01_

## Session-closing items

- ~~Fix `origin` remote~~ → Done: `https://github.com/rohit-naik36/TokenOpt.git`,
  `main` pushed (all 11 commits)

## Immediate

1. **Pipeline stage unit tests** — compressor, cache (hits/eviction/Redis),
   router (rules + complexity), RAG optimizer, few-shot selector, summarizer
2. **Integration tests** — mock OpenAI/Anthropic-compatible servers
   (responses library) exercising the full drop-in flow incl. cache persistence
3. **README** — complete usage examples: drop-in, factory, local client,
   configuration reference
4. **Build verification** — `python -m build` (sdist/wheel); `pip install -e .`
   already verified

## Short term (Phase 2)

- **Router** — per-model cost/latency tracking, dynamic routing
- **Cache** — persistence (Redis done, add file-backed), better eviction
- **Summarizer** — pluggable summarization model
- **Compressor** — real LLMLingua integration + improved heuristics
- **Local client** — streaming support (`stream=True` passthrough is stubbed
  but responses are not streamed through base client)
- **Observability** — Prometheus exporter option, cost tracking per project/model

## Longer term (post-v1)

- Prompt versioning/registry, A/B testing framework, team config sharing,
  web UI for experimentation
