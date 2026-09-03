# TokenOpt v2.0 — User Manual

A plain-English guide to installing, running, testing, and deploying TokenOpt v2.0.
You do not need to be a developer to follow this guide — every step is explained.

---

## 1. What TokenOpt Does (in plain English)

TokenOpt is a **smart middleman** between your application and an AI provider
(like OpenAI or Azure). Your app sends a chat request to TokenOpt instead of
sending it straight to the AI provider. TokenOpt then:

1. **Checks if the request is new** — if the exact same question was asked
   before (very recently), it reuses the previous answer prep work instead of
   doing it all again. This is the "cache".
2. **Shrinks the question** — it compresses your prompt (the text you send to
   the AI) so you pay for fewer tokens. It uses a technology called
   "headroom" plus its own built-in compressors.
3. **Checks nothing was lost** — before using a shrunk version, it verifies
   the meaning is still intact (this is the "fidelity check"). If the check
   fails, it **automatically uses your original text instead**, so you never
   get a worse answer because of compression.
4. **Sends the request to the AI provider**, returns the answer to you, and
   records what happened (audit log) so you can see how much you saved.

**The golden rule — "fails open":** if anything goes wrong (no AI provider
configured, no cache available, compression fails), TokenOpt simply forwards
your request unchanged. Your application never breaks because of TokenOpt.

---

## 2. What You Need Before You Start

- **A computer** running Windows, macOS, or Linux (this guide shows Windows
  commands; on Mac/Linux use `python3` instead of `python` and `/` instead of
  `\`).
- **Python 3.10 or newer** installed.
  - To check: open a terminal and run `python --version`.
  - If not installed, download it from https://www.python.org/downloads/
    (on Windows, tick "Add Python to PATH" during install).
- **An internet connection** (only needed to download the Python packages the
  first time).

---

## 3. Step-by-Step Installation

### Step 1: Put the files in one folder

Make sure these files are in the same folder (this is your "project folder"):

```
tokenopt_proxy_v2.py     ← the main program
provider_client_v2.py    ← talks to AI providers
persistence_layer_v2.py  ← saves records (audit log + cache)
fidelity_validator_v2.py ← checks compression quality
requirements.txt         ← list of extra packages to install
```

### Step 2: Create a private environment (recommended)

A "virtual environment" is a private copy of Python for this project, so
TokenOpt's packages never interfere with other programs on your computer.

Open a terminal inside the project folder and run:

```
python -m venv venv
```

Then activate it:

- **Windows:** `venv\Scripts\activate`
- **Mac/Linux:** `source venv/bin/activate`

You will see `(venv)` appear at the start of your terminal line.

### Step 3: Install the required packages

```
pip install -r requirements.txt
pip install "headroom-ai>=0.33.0"
```

If there is no `requirements.txt`, run:

```
pip install fastapi uvicorn[standard] pydantic httpx pyjwt redis aiokafka asyncpg "headroom-ai>=0.33.0"
```

> **Tip:** the headroom package is what does the smart compression. If it is
> not installed, TokenOpt still works — it just falls back to its built-in
> simpler compressor. No error, no breakage.

### Step 4: Check it works (health test)

```
python -c "import tokenopt_proxy_v2 as tp; print('module loads OK')"
```

If you see `module loads OK`, installation is complete.

---

## 4. Configuration (Environment Variables)

TokenOpt is controlled by settings called **environment variables**. You set
them in the terminal before starting the program, or in a `.env` file / Docker
settings if you deploy to a server.

**Important:** if you type a wrong value (for example a letter where a number
is expected), TokenOpt **does not crash** — it ignores the bad value, prints a
warning, and uses the safe default instead.

### 4.1 The settings table

| Setting | What it does | Default | Valid values |
|---|---|---|---|
| `JWT_SECRET` | Secret key that locks your API (see section 6) | `change-me-in-production` | any long random text |
| `OPENAI_API_KEY` | Your OpenAI key (if using OpenAI) | empty | your key |
| `AZURE_OPENAI_KEY` | Your Azure key (if using Azure) | empty | your key |
| `AZURE_OPENAI_ENDPOINT` | Your Azure endpoint URL | empty | your URL |
| `ANTHROPIC_API_KEY` | Your Anthropic key (if using Claude) | empty | your key |
| `FIDELITY_THRESHOLD` | How "safe" the quality check is, 0.0–1.0. Higher = stricter (less compression but safer) | `0.995` | 0.0 – 1.0 |
| `ENABLE_LLM_JUDGE` | Use the AI itself to double-check compressed text (slower, more thorough) | `true` | true / false / 1 / yes / on |
| `ENABLE_HEADROOM` | Use the headroom smart compressor | `true` | true / false / 1 / yes / on |
| `HEADROOM_MIN_TOKENS` | Only compress requests this size or bigger (small ones are not worth it) | `100` | any whole number |
| `HEADROOM_TARGET_RATIO` | How much of the original size to aim for, 0.1–0.95 (0.5 = aim for half the tokens) | `0.5` | 0.1 – 0.95 |
| `MAX_CONCURRENT_REQUESTS` | How many requests TokenOpt handles at the same time. Negative values are clamped to 1 | `100` | 1 or more |
| `REQUEST_TIMEOUT` | Seconds to wait for the AI provider before giving up | `60.0` | any number |
| `POSTGRES_DSN` | Where to store the permanent audit log (a PostgreSQL database) | `postgresql://tokenopt:password@localhost:5432/tokenopt` | a database address |
| `REDIS_URL` | Where to store the fast cache (a Redis server) | `redis://localhost:6379/0` | a server address |
| `REDIS_CLUSTER` | Use Redis in cluster mode | `false` | true / false |
| `KAFKA_BROKERS` | Where to send event messages (Kafka) | `localhost:9092` | a server address |
| `ENCRYPTION_KEY` | Extra key for encrypting stored data | empty | random text |

### 4.2 What happens if a service is unavailable

TokenOpt degrades gracefully — you never lose service:

| Service | If unavailable, TokenOpt uses... |
|---|---|
| PostgreSQL (audit log) | a built-in temporary record that keeps the last 10,000 entries |
| Redis (cache) | a built-in temporary cache with the same "remember for a while" behavior |
| Kafka (events) | nothing — events are simply skipped |
| AI provider keys | fails open: requests are still accepted and returned unchanged |

---

## 5. How to Run TokenOpt

### 5.1 Quick start (with defaults)

```
uvicorn tokenopt_proxy_v2:app --host 0.0.0.0 --port 8000
```

You should see a message that the server is running. TokenOpt is now listening
for requests on **http://localhost:8000**.

### 5.2 Run with your own settings

**Windows (PowerShell):**

```
$env:JWT_SECRET = "make-up-a-long-secret-string"
$env:OPENAI_API_KEY = "sk-..."
uvicorn tokenopt_proxy_v2:app --host 0.0.0.0 --port 8000
```

**Mac/Linux:**

```
export JWT_SECRET="make-up-a-long-secret-string"
export OPENAI_API_KEY="sk-..."
uvicorn tokenopt_proxy_v2:app --host 0.0.0.0 --port 8000
```

> **Where is the Swagger page?** FastAPI gives you a clickable test page at
> http://localhost:8000/docs — you can try every endpoint from your browser.

---

## 6. Security — Who Is Allowed to Use It

TokenOpt protects its API with a token system called **JWT**:

- Your app must send an **Authorization** header with a token.
- The token must be signed with the same `JWT_SECRET` you set. If you change
  the secret, old tokens stop working.
- Tokens have an **expiry time** (expired tokens are rejected).
- The token normally contains a `tenant_id` — who is using the system
  (e.g. which customer). If it is missing, TokenOpt uses `default` and still
  works.

**You must change `JWT_SECRET` before going live.** Anyone who knows the
default secret can generate valid tokens.

---

## 7. How to Send a Request (Testing)

TokenOpt speaks the standard OpenAI "chat completions" language, so anything
that can call OpenAI can call TokenOpt — you just change the address.

### 7.1 Create a test token (for trying it out)

Install the helper package once:

```
pip install pyjwt
```

Then generate a token valid for 1 hour (save the output):

```
python -c "import jwt,time; print(jwt.encode({'tenant_id':'demo','sub':'tester','exp':int(time.time())+3600}, 'change-me-in-production', algorithm='HS256'))"
```

> Use the same secret you started the server with.

### 7.2 Send a test request

**Windows (PowerShell):**

```
$token = "PASTE-YOUR-TOKEN-HERE"

$body = @{
  model = "gpt-4"
  messages = @(@{ role = "user"; content = "Summarize these logs: ERROR timeout attempt 1; WARN retry; ERROR timeout attempt 2" })
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Uri "http://localhost:8000/v1/chat/completions" -Method Post -Headers @{ Authorization = "Bearer $token" } -ContentType "application/json" -Body $body
```

**Mac/Linux:**

```
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer PASTE-YOUR-TOKEN-HERE" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4","messages":[{"role":"user","content":"Summarize these logs: ERROR timeout attempt 1; WARN retry; ERROR timeout attempt 2"}]}'
```

### 7.3 What you should see in the answer

The reply is a normal chat-completion answer plus a `tokenopt` section that
tells you what happened:

| Field | What it means |
|---|---|
| `savings_pct` | How much of the prompt size was saved (example: 38.5 = 38.5% smaller) |
| `original_tokens` / `optimized_tokens` | Size before / after compression |
| `techniques` | What was used (`headroom:...` = smart compressor, `cache_hit` = repeated question, `safe_compression` = safe fallback) |
| `fidelity_score` | How confident we are the meaning was kept (0.995 ≈ very confident) |
| `was_rolled_back` | `true` = the original text was used because the check failed (you always get a correct answer) |
| `cache_hit` | `true` = this exact request was seen recently and prep work was reused |

### 7.4 Other useful pages to test

| Address | What it is for |
|---|---|
| `GET http://localhost:8000/health` | Is TokenOpt alive? Shows the state of every service (validator, providers, database, cache) |
| `POST http://localhost:8000/v1/tokenopt/validate?prompt=...` | Try a prompt and preview how much it would shrink — **no AI call, no cost** |
| `GET http://localhost:8000/v1/tokenopt/stats` | Summary of usage: providers, cache, savings, fidelity |
| `GET http://localhost:8000/v1/tokenopt/rollbacks` | List of times TokenOpt decided to use the original text (safety events) |

### 7.5 Request options (all optional except model and messages)

| Option | Effect |
|---|---|
| `temperature` | Creativity, 0.0–2.0 (default 0.7) |
| `max_tokens` | Maximum answer length (1 or more) |
| `top_p` | Answer variety, 0.0–1.0 (default 1.0) |
| `frequency_penalty` / `presence_penalty` | Style tweaks, -2.0 to 2.0 |
| `stream` | `true` = answer arrives piece by piece (SSE) |
| `optimization_level` | `standard` (default), `aggressive` (shrink more), or `conservative` (shrink less) |
| `skip_optimization` | `true` = send the request through untouched |
| `fidelity_threshold` | A stricter/looser safety bar for this one request (0.0–1.0) |
| `preferred_provider` | Which AI provider to try first (if several are configured) |

Wrong values (for example temperature = 5) are rejected with a clear error
message — they are never silently ignored.

---

## 8. Everyday Operations

### Starting and stopping
- **Start:** run the uvicorn command from section 5.
- **Stop:** press `Ctrl + C` in the terminal window.

### Checking it is healthy
Open http://localhost:8000/health in a browser. Look for:

- `fidelity_validator` — `ok` (quality checking is working)
- `audit_db` — `fallback` means the temporary recorder is in use (fine for
  testing; see section 9 for the permanent version)
- `cache` — should say it is working (temporary cache is fine for testing)

### Seeing your savings
Open http://localhost:8000/v1/tokenopt/stats. The page shows how many tokens
and how much money your compressed requests saved.

### Reading the audit log
The server prints one line per request in the terminal:
`AUDIT: { ... original_prompt, optimized_prompt, tokens_saved ... }`.
This is your record of what went in and what came out.

---

## 9. Going to Production (Deployment)

When you are ready to let real users use TokenOpt, work through this checklist.
The full technical details are in `DEPLOYMENT_GUIDE.md`.

### 9.1 Must-do list (security)

- [ ] **Change `JWT_SECRET`** to a long random value (never the default).
- [ ] **Add your real AI provider keys** (`OPENAI_API_KEY` or
      `AZURE_OPENAI_KEY` + `AZURE_OPENAI_ENDPOINT`).
- [ ] **Set `ENCRYPTION_KEY`** if you want stored data encrypted.
- [ ] Keep keys and secrets in a secret manager or `.env` file that is NOT
      committed to code.

### 9.2 Must-do list (reliability)

- [ ] **Give it a real PostgreSQL database** — set `POSTGRES_DSN` so your
      audit log survives restarts.
- [ ] **Give it a real Redis** — set `REDIS_URL` so the cache is shared
      between server instances (if you run more than one copy).
- [ ] (Optional) **Set up Kafka** — set `KAFKA_BROKERS` if you want event
      messages for monitoring tools.
- [ ] **Run behind a web server** (for example Nginx or a cloud load
      balancer) that handles HTTPS. The token travels over HTTP otherwise.
- [ ] **Run several copies** of TokenOpt behind the load balancer so that if
      one copy stops, the others keep answering.

### 9.3 Using Docker (recommended)

A ready-made container recipe lives in `DEPLOYMENT_GUIDE.md`. The short
version:

```
docker build -t tokenopt .
docker run -d -p 8000:8000 -e JWT_SECRET="long-random-secret" tokenopt
```

### 9.4 Tuning after go-live

- If you notice the AI answers seem less faithful, **raise** `FIDELITY_THRESHOLD`
  (e.g. to 0.998) — compression becomes more careful.
- If you want bigger savings and the answers still look great, **lower**
  `HEADROOM_TARGET_RATIO` (e.g. to 0.4).
- Use the `/v1/tokenopt/validate` page to preview exactly how much a prompt
  would shrink before you change any settings.

---

## 10. Troubleshooting (common questions)

| Symptom | Cause / fix |
|---|---|
| `module loads OK` prints a warning about invalid env value | A setting had a bad value; the safe default is being used. Fix the spelling in your env file. |
| Health page shows `providers: []` | No AI provider keys are set. Requests still work and are returned unchanged (fails open), but nothing will be compressed or sent to an AI. |
| The server will not start and shows an error mentioning "port" | The port is already in use. Choose another one: `--port 8001`. |
| Answer has no `tokenopt` section | You are probably calling a real AI provider directly, not TokenOpt's address. Check the URL. |
| `savings_pct` is 0.0 | The request was too short to compress (under `HEADROOM_MIN_TOKENS`), or `skip_optimization` was set, or the fidelity check rolled it back — all normal. |
| `was_rolled_back: true` | The safety check decided to use your original text. This is TokenOpt protecting you — nothing is wrong. |
| Logged out / requests rejected (401) | The token expired or `JWT_SECRET` changed. Generate a new token with the current secret. |
| Wrong answer or missing content in responses | TokenOpt returns the AI's answer as-is; this usually means the AI provider itself returned that. |

---

## 11. What All the Tests Mean (and How to Run Them)

Everything below was run and is green (41 QE checks + 17 full-execution checks).

| Test | What it proves | How to run |
|---|---|---|
| QE suite | Every setting and every request option: valid, invalid, boundary, and behavior (caching, rollback, circuit breaker, failover, streaming) | `python qe_suite.py` |
| Full execution check | The whole program boots and every endpoint works end-to-end | `python full_check.py` |
| Headroom integration | The smart compressor works, rolls back safely, and can be switched off | `python test_headroom_integration.py` |
| Headroom cache | Repeated identical requests reuse cached work | `python test_headroom_cache.py` |

Typical results you should see:

- QE suite: `PASSED: 41   FAILED: 0`
- Full check: `FULL EXECUTION CHECK PASSED` (17/17)
- Integration: tests 1–5 all print and finish without errors
- Cache: `miss` then `hit` with the same token counts

---

## 12. Where to Learn More

| Document | What it covers |
|---|---|
| `DEPLOYMENT_GUIDE.md` | Docker, servers, scaling — technical setup details |
| `API_SPECIFICATION.md` | The exact technical format of every request and response |
| `OPERATIONS_RUNBOOKS.md` | What to do when things go wrong in production |
| `SECURITY_COMPLIANCE.md` | Security model, token rules, encryption |
| `ARCHITECTURE_DECISION_RECORDS.md` | Why TokenOpt was designed this way |
| `COST_ANALYSIS_FREE_VS_PAID.md` | How much money the compression saves |
