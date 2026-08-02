# TokenOpt SDK — Team Testing Guide (v0.1.0)

> Shared with the QA / integration team. This guide covers everything a
> tester needs to validate **TokenOpt v0.1.0** (the first public release,
> live on PyPI) — from installation to deep feature checks, including
> expected outputs for every scenario.
>
> Companion docs: `docs/UAT.md` (release acceptance checklist, maintained
> by the Release Manager) and `README.md` (user documentation).
>
> Total time for the full pass: **~60–90 minutes** per environment.

---

## 1. What you are testing

TokenOpt is a Python SDK that makes LLM calls cheaper and faster by
optimizing prompts automatically, and it is a **drop-in replacement** for
the official OpenAI / Anthropic SDKs:

```python
# before
from openai import OpenAI

# after — one import change, everything else identical
from tokenopt import OpenAI
```

For every request it runs an optimization pipeline: **model routing →
prompt compression → conversation summarization → semantic caching →
RAG chunk optimization → few-shot selection**, then reports metrics
(tokens saved, latency split, estimated cost).

**v0.1.0 scope:** non-streaming chat completions (OpenAI), messages
(Anthropic), local OpenAI-compatible servers, in-memory + optional Redis
cache, offline automated test suite. See §10 for known limitations.

**Contract you must verify everywhere:** optimization is *fails open* —
if any optimization stage errors, the underlying request still succeeds.
The SDK never stores or logs API keys.

---

## 2. Prerequisites

| Item | Requirement |
|------|-------------|
| Python | **3.10, 3.11, or 3.12** (`python --version`) |
| Git | any recent version (for the repo clone / `git`-install check) |
| API keys | `OPENAI_API_KEY` (OpenAI tests), `ANTHROPIC_API_KEY` (Anthropic tests) |
| Optional | Ollama running locally (`ollama serve`) or any OpenAI-compatible server (vLLM, llama.cpp, LM Studio) |
| Network | Required for cloud-provider scenarios; **all automated tests are offline** |
| OS | Windows / macOS / Linux — commands below given for both PowerShell and bash |

> **No keys yet?** You can still complete Parts A and B fully, and most of
> Parts C–D, by pointing the SDK at a local OpenAI-compatible stub server —
> see **Appendix A** (no external dependencies, Python stdlib only).

---

## 3. Setup (5 minutes)

### 3.1 Clone + virtual environment

```bash
git clone https://github.com/rohit-naik36/TokenOpt.git
cd TokenOpt
python -m venv .venv
```

Activate:

- macOS/Linux: `source .venv/bin/activate`
- Windows PowerShell: `.venv\Scripts\Activate.ps1`

### 3.2 Install — choose one

```bash
# A. From PyPI (what your users will do) — core providers + all features
pip install tokenopt

# B. From source (recommended for testing examples from the repo)
pip install -e .
```

**Extras** (see `README.md`): `[local]` (native Ollama), `[cache]`
(Redis), `[semantic]` (sentence-transformers embeddings), `[compression]`
(LLMLingua), `[all]` (everything), `[dev]` (test/lint/type tools).
For this guide, `pip install -e ".[dev]"` covers everything:

```bash
pip install -e ".[dev]"
```

### 3.3 API keys

```bash
# macOS/Linux
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...

# Windows PowerShell
$env:OPENAI_API_KEY = "sk-..."
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

---

## 4. Test matrix at a glance

| # | Part | Test | Offline? | Time |
|---|------|------|----------|------|
| A1 | A | Import + version | ✅ | 1 min |
| A2 | A | Automated suite (167 tests) | ✅ | 2–3 min |
| A3 | A | Fresh-venv PyPI install | ✅ | 3 min |
| B1 | B | `quickstart.py` — drop-in + metrics | ❌ (key) | 2 min |
| B2 | B | `openai_basic.py` — compression OFF vs ON + cache | ❌ (key) | 3 min |
| B3 | B | `anthropic_basic.py` — summarization | ❌ (key) | 3 min |
| B4 | B | `local_basic.py` — local models | ✅* | 3 min |
| B5 | B | `pipeline_config.py` — routing + reasons | ❌ (key) | 4 min |
| B6 | B | `metrics_observability.py` — metrics + callback | ❌ (key) | 3 min |
| C1 | C | Drop-in code swap (your own snippet) | ❌ (key) | 5 min |
| C2 | C | Fail-open / error handling | ✅ (stub) | 5 min |
| C3 | C | Security — no keys in output | ✅ (stub) | 3 min |
| D1 | D | Routing precedence contract | ❌ (key) | 5 min |
| D2 | D | Config feature gates | ✅ | 5 min |

\* `local_basic.py` needs a running local server (Ollama or stub).

---

# Part A — Automated suite (offline, deterministic)

## A1 — Import and version

```bash
python -c "import tokenopt; print(tokenopt.__version__)"
```

**PASS if:** prints `0.1.0` and no warnings.

## A2 — Full automated suite

```bash
pytest tests/ -q
```

**PASS if:** the run ends with `167 passed`, and the coverage line reports
`94%` (the ≥80% gate is enforced by pytest itself — a lower value fails
the run).

## A3 — Fresh-venv PyPI install (what users experience)

In a second, brand-new venv (no `-e`):

```bash
python -m venv /tmp/tokenopt-check        # macOS/Linux
# python -m venv C:\temp\tokenopt-check   # Windows
python -m pip install tokenopt
python -c "from tokenopt import OpenAI, Anthropic, LocalClient, create_client, TokenOptConfig; print('imports OK')"
```

**PASS if:** `imports OK` prints. Also try one extra:
`pip install "tokenopt[local]"` then `python -c "import ollama"` succeeds.

---

# Part B — Example scripts (live demos)

All examples live in `examples/` and print human-readable metric blocks.
Run each from the repo root: `python examples/<name>.py`.

## B1 — `examples/quickstart.py` (drop-in + metrics)

**What it proves:** one import change; the pipeline runs; metrics print.

```bash
python examples/quickstart.py
```

**PASS if — all of:**
- Response text prints (model actually answered)
- A `Request metrics:` block shows: `Model`, `Cache hit: No`,
  `Compression:`, `Tokens:`, `Latency:`, `Estimated cost:`
- `Explain:` lines describe what happened (e.g. routing reason)
- No `Traceback`; no raw JSON log spam (logs are quiet by default)

## B2 — `examples/openai_basic.py` (compression + cache)

```bash
python examples/openai_basic.py
```

**PASS if — all of:**
- "Compression OFF vs ON" comparison: **ON shows fewer tokens** than OFF
  (expected ~44% reduction on the built-in long prompt; exact numbers vary)
- Request 1 (cache section): `Cache hit: No`
- Request 2 (identical): `Cache hit: Yes`, latency collapses to TokenOpt
  overhead only (~ms), response content identical to request 1
- Aggregated summary prints requests, cache hit rate (≈0.5), avg tokens
  reduced, total estimated cost

## B3 — `examples/anthropic_basic.py` (summarization)

```bash
python examples/anthropic_basic.py
```

**PASS if — all of:**
- A real Claude reply renders (content blocks joined, no raw list output)
- `Model:` shows `claude-3-5-haiku` — **never** a `gpt-*` model
  (cross-provider routing must not happen)
- Metrics show the 5-turn history exceeded the (deliberately low)
  150-token threshold and was **summarized** (older turns → a compact
  "Previous conversation summary" system message; tokens reduced)

## B4 — `examples/local_basic.py` (local models)

Requires a local server. Options:

- **Ollama:** just run it (default `http://localhost:11434`)
- **Any OpenAI-compatible server** (vLLM / llama.cpp / LM Studio):
  `export TOKENOPT_EXAMPLE_BASE_URL=http://localhost:8000/v1`
- **No server at all:** use the stub in Appendix A, then point the env var
  at `http://127.0.0.1:8787/v1`

```bash
python examples/local_basic.py
```

**PASS if — all of:**
- Local model replies; compression reduced the long prompt's tokens
- Request 1 `Cache hit: No` → request 2 `Cache hit: Yes` (no second
  inference call)
- The "does NOT persist across separate program executions" note prints
- Metrics/cost estimation work exactly like cloud providers

## B5 — `examples/pipeline_config.py` (routing + reasons)

```bash
python examples/pipeline_config.py
```

**PASS if — all of:**
- Math prompt → `Model: o1-mini`, reason `math_tasks` (custom rule)
- Code prompt → `Model: gpt-4o`, reason `code_tasks`
- Simple + complex prompts → model **preserved** (default `gpt-4o-mini`),
  reason `preserved (no rule matched)`
- "No custom rules" section → complexity routing assigns a model, reason
  `complexity-based (low|medium|high)`
- Routing OFF vs ON comparison shows OFF stays on the single manual model
- An explicit `model=` passed by the caller is **never** overridden

## B6 — `examples/metrics_observability.py` (metrics + callback)

```bash
python examples/metrics_observability.py
```

**PASS if — all of:**
- Request 1: full pipeline + model call (`pipeline_latency_ms` > 0,
  `model_latency_ms` reported)
- Request 2 (identical): `Cache hit: Yes`, total ≈ overhead only
- The field-by-field annotations print and match the values in the metrics
  block (e.g. `original_tokens` → `optimized_tokens` = `tokens_saved`)
- The `[callback]` line prints once per request with model/tokens/routed/
  cache-hit values — the `metrics_callback` hook works
- Standalone utilities print: `Message tokens: N`, `Estimated cost ... USD`

---

# Part C — Contract checks

## C1 — Drop-in swap (write this snippet yourself)

Create `my_dropin_test.py`:

```python
from tokenopt import OpenAI, TokenOptConfig

config = TokenOptConfig(
    compression_ratio=0.5,
    cache_enabled=True,
    enable_routing=True,
)
client = OpenAI(config=config)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Explain semantic caching in one sentence."}],
)
print(response.choices[0].message.content)
print(client.get_metrics_summary())
```

**PASS if:** identical API shape to `openai.OpenAI` (no extra imports, no
`await`, no keyword changes); response prints; summary shows model,
cache status, token reduction.

## C2 — Fail-open & error handling (stub server recommended)

| Scenario | Expected result |
|----------|-----------------|
| Invalid API key | Provider error raised cleanly; summary `error_rate` becomes 1.0; **no crash inside TokenOpt** |
| Invalid `base_url` (e.g. port 1) | Clear connection error — not an internal exception |
| Stage failure (simulate by monkey-patching a stage to raise) | Request **still succeeds** — optimization errors never block the call |
| Missing API key entirely | Clear `AuthenticationError`/key message, not a confusing internal error |

## C3 — Security: no secrets leak

Run any example while capturing output to a file, then:

```bash
grep -ri "sk-ant\|sk-proj\|sk-" output.log   # should find nothing
```

**PASS if:** no key material appears in stdout, logs, or metrics; JSON log
events (`request_completed`) contain metrics only, never keys.

---

# Part D — Deep feature verification

## D1 — Routing precedence (Decision 24 contract)

Write a test with a custom rule matching nothing:

```python
from tokenopt import OpenAI, RoutingRule, TokenOptConfig

config = TokenOptConfig(
    enable_routing=True,
    routing_rules=[RoutingRule(name="never", condition=lambda q, m: False, model="gpt-4o")],
)
client = OpenAI(config=config)
client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}])
m = client.metrics_collector.get_recent(1)[0]
print(m.model, m.routing_reason)   # expect: gpt-4o-mini 'preserved (no rule matched)'
```

**PASS if:** `gpt-4o-mini preserved (no rule matched)` — the caller's model
is never rewritten. Repeat with `claude-3-5-haiku` on `tokenopt.Anthropic`
and confirm it stays `claude-*` (no `gpt-*` rewrite to a nonexistent model).

## D2 — Config feature gates

```python
from tokenopt import OpenAI, TokenOptConfig

client = OpenAI(config=TokenOptConfig(
    enable_compression=False, cache_enabled=False, enable_routing=False,
    enable_summarization=False, observability_enabled=False,
))
# send a request -> metrics should show 0 tokens saved, no routing applied
```

**PASS if:** the client behaves as a thin passthrough — response equals the
unoptimized baseline, and disabling optimization never changes the
response text (only cost/latency).

---

# Part E — Known limitations (v0.1.0 — NOT bugs)

- **Streaming:** `stream=True` is passthrough for local clients; the
  base OpenAI/Anthropic flows are non-streaming in v0.1.0.
- **Cache persistence:** in-memory cache lives on the client instance —
  it does not survive a process restart (Redis-backed cache via
  `[cache]` extra is the persistent option).
- **Semantic cache without extras:** falls back to exact-match hashing
  unless `[semantic]` is installed.
- **Python versions:** 3.10–3.12 tested; 3.13+ untested.
- **Public API:** pre-1.0 — may evolve; follow CHANGELOG.

---

# Appendix A — Offline stub server (no API keys needed)

Python-stdlib-only OpenAI-compatible endpoint for Parts B–D testing:

```python
# stub_server.py — run:  python stub_server.py
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        content = "Stub reply to: " + body["messages"][-1]["content"][:80]
        payload = {
            "id": "chatcmpl-stub", "object": "chat.completion",
            "model": body.get("model", "stub"), "choices": [
                {"index": 0, "message": {"role": "assistant", "content": content},
                 "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        }
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # keep console clean
        pass

HTTPServer(("127.0.0.1", 8787), Handler).serve_forever()
```

Then:

```bash
export OPENAI_BASE_URL=http://127.0.0.1:8787/v1        # macOS/Linux
# $env:OPENAI_BASE_URL = "http://127.0.0.1:8787/v1"    # PowerShell
export TOKENOPT_EXAMPLE_BASE_URL=http://127.0.0.1:8787/v1
```

Run examples B1, B2, B5, B6 with the stub — the full pipeline (routing,
compression, cache, metrics) runs locally with zero external API calls.
Note: routing rules matching cloud models will still route by rules, but
the stub answers every model name, so all requests succeed.

---

# Appendix B — Bug report template

Use a GitHub issue on `rohit-naik36/TokenOpt` (label: `bug`) with:

```markdown
**Environment:** Python x.y.z · OS · install method (pip install tokenopt / -e .)
**Scenario:** which part (A1–D2) / example / custom snippet
**Command run:** ...
**Expected:** ...
**Actual:** (paste output, especially the metrics block and any Traceback)
**Reproducible:** always / sometimes / once
**Any keys in output?** yes / no (must be NO — redact first)
```

---

# Sign-off

| Tester | Date | Environment (OS + Python) | Result |
|--------|------|----------------------------|--------|
| | | | ☐ Pass / ☐ Fail |
| | | | ☐ Pass / ☐ Fail |

**Defects found:** open GitHub issues for each; list them here:

```
None.
```

**Questions / observations** (not defects, but worth sharing):

```
None.
```

---

_Companion: `docs/UAT.md` — release acceptance checklist · `README.md` —
user docs · `SECURITY.md` — responsible disclosure._
