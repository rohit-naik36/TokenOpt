# Roadmap

_Last updated: 2026-08-01_

## Phase 1 — Core infrastructure (DONE)
- [x] Project setup (pyproject, extras)
- [x] Config, token counting, embeddings
- [x] Pipeline framework + all stages (compressor, summarizer, cache, router, RAG, few-shot)
- [x] Observability (metrics, logging, cost estimation)
- [x] OpenAI / Anthropic / Local client wrappers
- [x] Client factory + package exports
- [x] Baseline unit tests (23)

## Phase 2 — Hardening & enhancements (NEXT)
- [ ] Pipeline stage unit tests
- [ ] Integration tests (mock servers)
- [ ] README + docs
- [ ] Build/packaging verification
- [ ] Router: cost/latency tracking, dynamic routing
- [ ] Cache: file persistence, better eviction
- [ ] Summarizer: pluggable summarization model
- [ ] Compressor: real LLMLingua integration
- [ ] Local client: streaming
- [ ] Prometheus exporter option

## Post-v1 — Advanced
- [ ] Prompt versioning/registry
- [ ] A/B testing framework
- [ ] Team config sharing
- [ ] Web UI for experimentation
