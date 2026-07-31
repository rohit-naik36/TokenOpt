# Architecture Decisions

_Last updated: 2026-08-01_

| # | Decision | Rationale | Status |
|---|----------|-----------|--------|
| 1 | Python SDK as drop-in wrapper | Zero code changes for users; `from tokenopt import OpenAI` | Accepted |
| 2 | Cache: in-memory LRU + optional Redis | Simple for personal use, scalable path exists | Accepted |
| 3 | Compression: heuristic first, optional ML (LLMLingua) | No heavy deps by default; pluggable | Accepted |
| 4 | Routing: rule-based + complexity scoring, runs FIRST in pipeline | Transparent and configurable; model choice precedes compression | Accepted |
| 5 | Observability built-in + callbacks | No external deps required | Accepted |
| 6 | Pipeline stages enabled/disabled via `TokenOptConfig` | Modularity; stages are swappable | Accepted |
| 7 | `LocalClient` normalizes Ollama responses to OpenAI chat shape (`choices[0].message.content`, `usage`) | Base client, cache, and metrics work unchanged across backends | Accepted |
| 8 | `LocalClient` drops the cloud router by default | Default routing rules target cloud models (gpt-*/claude*) and would break local servers; only routing rules targeting local models are honored | Accepted |
| 9 | Factory auto-detects provider from model prefix (`gpt-`/`o1-`/`o3-` → openai, `claude` → anthropic, else local) or base_url containing `11434` | One entry point for multi-model routing; sensible defaults | Accepted |
| 10 | Unknown models fall back to `cl100k_base` encoding in token counter | Robustness for local/private model names | Accepted |
| 11 | Never modify the Git remote automatically; before any push verify `git remote -v`, ensure URL matches `github.com/<username>/<repository>.git`; if missing/malformed, stop and ask for approval; never guess or rewrite the remote URL | Prevents accidental pushes to wrong/malicious remotes; remote config is user-owned | Accepted |

## Rejected / deferred

- **Streaming through base client** — deferred to Phase 2; local client passes
  `stream` kwarg but base flow is non-streaming
- **Async clients** — out of scope for v0.1; sync only
- **Prompt versioning registry** — post-v1

## Notes

- Decisions are append-only; supersede with a new entry rather than editing old ones.
