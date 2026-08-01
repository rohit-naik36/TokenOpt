# TokenOpt — User Acceptance Testing (UAT) Checklist

> Permanent manual acceptance checklist for **every release** of TokenOpt.
> Run through all scenarios on a clean machine (or fresh virtual
> environment) before tagging a release. "Pass" means the documented
> behavior was observed; any deviation is a release blocker unless the
> Release Manager records an exception in the release notes.

**Baseline:** Python ≥ 3.10 · OS-independent (Windows, macOS, Linux) ·
offline-safe except scenarios that explicitly call a real provider or a
running local server.

---

## 0. Environment

- [ ] Fresh virtual environment created (`python -m venv .venv`)
- [ ] `python --version` reports 3.10, 3.11, or 3.12
- [ ] Clone or checkout the release commit

---

## 1. Installation

- [ ] `pip install -e .` succeeds; `python -c "import tokenopt; print(tokenopt.__version__)"`
      prints the release version
- [ ] `pip install -e ".[local]"` and `pip install -e ".[cache]"` succeed
      (optional extras)
- [ ] `pip install git+https://github.com/rohit-naik36/TokenOpt.git` succeeds
      in a second, clean venv (README-documented command)
- [ ] `import tokenopt` works from a directory outside the repo (installed,
      not just cwd)

## 2. Quick Start

- [ ] `python examples/quickstart.py` runs with `OPENAI_API_KEY` set
- [ ] Output contains: response text, a `Request metrics:` block (Model,
      Cache hit, Compression, Tokens, Latency, Estimated cost) — **not**
      raw JSON logs
- [ ] No `Traceback` or unexpected warnings
- [ ] Without `OPENAI_API_KEY`, the failure is a clear API-key error
      (not a confusing internal error)

## 3. OpenAI

- [ ] `python examples/openai_basic.py` completes two requests
- [ ] Request 1 reports `Cache hit: No`
- [ ] Request 2 reports `Cache hit: Yes` and shows near-zero overhead latency
- [ ] Aggregated block prints (requests, cache hit rate, avg tokens reduced,
      total estimated cost)

## 4. Anthropic

- [ ] `python examples/anthropic_basic.py` runs with `ANTHROPIC_API_KEY` set
- [ ] Response text renders (Anthropic message blocks joined correctly)
- [ ] `Model:` shows the requested `claude-*` model (no cross-provider routing)

## 5. Local / Ollama

- [ ] With Ollama running: `python examples/local_basic.py` uses the default
      URL and returns the local model's reply
- [ ] Without the `[local]` extra, the error message suggests
      `pip install tokenopt[local]`
- [ ] With `TOKENOPT_EXAMPLE_BASE_URL` pointing at an OpenAI-compatible
      server (vLLM/llama.cpp/LM Studio), the same script works

## 6. Cache verification

- [ ] Two identical requests on one client: miss then hit (cache hit rate
      0.5 in the summary)
- [ ] The example's note about per-instance caching is printed — verify a
      **second program execution** does not reuse the cache
- [ ] `client.clear_cache()` (or a new client) forces a fresh miss

## 7. Routing verification

- [ ] `python examples/pipeline_config.py` routes the math query to
      `o1-mini` (custom rule) and the generic query via complexity fallback
- [ ] `Model:` in the metrics block matches the routed model
- [ ] Anthropic and Local clients never route to `gpt-*` models

## 8. Metrics verification

- [ ] Per-request block distinguishes compression **attempted** vs
      **effective** (e.g. short prompt: attempted / no reduction,
      0 tokens, 0.0%)
- [ ] Long prompt shows `tokens saved > 0` and a percentage
- [ ] Latency split: `total ≈ model + TokenOpt overhead`; overhead is
      reported in the same units and small relative to model latency
- [ ] Structured JSON logging still available in production: with the SDK
      at INFO level, `request_completed` events contain
      `compression_attempted`, `compression_effective`, `tokens_saved`,
      `reduction_percentage`, `model_latency_ms`

## 9. Error handling

- [ ] Invalid API key → provider error raised, `error_rate` becomes 1.0 in
      the summary, no crash inside TokenOpt
- [ ] Pipeline failure (simulated) → request still succeeds (fail open)
- [ ] Invalid `base_url` → clear connection error, not an internal error
- [ ] No API key/secret ever appears in logs or metrics output

## 10. Clean uninstall

- [ ] `pip uninstall tokenopt` removes the package
- [ ] `import tokenopt` then fails with `ModuleNotFoundError`
- [ ] No leftover `tokenopt` files in `site-packages` (or an installed
      egg-link/dist-info only from the editable install, removed too)
- [ ] Example scripts still runnable via the repo checkout (they do not
      depend on the installed package at runtime beyond imports)

---

## Sign-off

| Role | Name | Date | Result |
|------|------|------|--------|
| Tester | | | ☐ Pass / ☐ Fail |
| Release Manager | | | ☐ Approved / ☐ Blocked |

Record deviations and exceptions below (each requires Release Manager sign-off):

```
None.
```
