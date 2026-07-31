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
| 12 | AI Session Management Policy: the repository is the single source of truth (never the conversation); the agent's primary responsibility is resumability; controlled shutdown triggered by milestone completion, ~40–60 interactions, ~60–90 min elapsed, multiple areas modified, or any natural stopping point — stop EARLY, validate (pytest/ruff/mypy/build), update all memory incl. `SESSION_STATE.md` and `TASK_QUEUE.md`, create a checkpoint, commit, push, hand over, and STOP | Prevents context exhaustion from destroying project knowledge; guarantees any AI engineer can resume from the repo alone | Accepted |
| 13 | `Anthropic` adapter scopes routing to Anthropic models only | The default router (Decision 4) targets `gpt-*` models; routing an Anthropic request to `gpt-*` sends a nonexistent model to the Anthropic API and breaks the drop-in contract out of the box. Mirrors Decision 8 (`LocalClient` drops cloud rules): only custom rules whose `model` contains `claude` are kept; otherwise no router runs | Accepted (M4 integration defect) |
| 14 | `chat` property nested exactly like the real SDK: `client.chat.completions.create(...)` | The documented drop-in contract (README, package docstring) is `client.chat.completions.create(...)`, but the property exposed `chat.create(...)` directly → `AttributeError` on the documented surface. Restores documented behavior; `chat_completion()` remains the direct method | Accepted (M4 integration defect) |
| 15 | Integration tests stub HTTP via `httpx.MockTransport` injected with `http_client=`; no new dependency | `httpx` is already a transitive dependency of the openai/anthropic SDKs. The M4 dev-dependency budget stays unspent; tests remain fully offline and CI-friendly | Accepted |
| 16 | `LocalClient` Ollama backend raises a clear, actionable error when the optional `ollama` package is missing; mypy overrides extended to `ollama.*` | CI (no optional extras) exposed a bare `ModuleNotFoundError` on `create_client(provider="local")` with the default URL; local env was masking it because `ollama` happened to be installed. Aligns with the fail-open/optional-extras philosophy: type gate and tests must not require optional packages (M1 precedent), and users get an install hint instead of a cryptic traceback | Accepted (M5 CI defect) |

## Rejected / deferred

- **Streaming through base client** — deferred to Phase 2; local client passes
  `stream` kwarg but base flow is non-streaming
- **Async clients** — out of scope for v0.1; sync only
- **Prompt versioning registry** — post-v1

## Notes

- Decisions are append-only; supersede with a new entry rather than editing old ones.
