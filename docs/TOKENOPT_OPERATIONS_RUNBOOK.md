# TokenOpt Operations Runbook (Standard A–Z Procedures)

This operations runbook specifies production deployment, configuration, runtime operations, failure recovery, and diagnostic procedures for the TokenOpt system (Gateway and Enterprise Proxy).

Every procedure conforms to standard operating structure:
- **PURPOSE**
- **PREREQUISITES**
- **EXACT COMMAND**
- **EXPECTED RESULT**
- **FAILURE SYMPTOM**
- **TROUBLESHOOTING**
- **VERIFICATION**

---

## Section A: Environment Provisioning & Python Venv Setup

- **PURPOSE**: Provision an isolated Python 3.11+ virtual environment for TokenOpt execution.
- **PREREQUISITES**: Python 3.11, 3.12, or 3.13 installed; Git installed.
- **EXACT COMMAND**:
  ```powershell
  # Windows PowerShell
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  python -m pip install --upgrade pip setuptools wheel
  ```
  ```bash
  # Linux / macOS
  python3 -m venv .venv
  source .venv/bin/activate
  python -m pip install --upgrade pip setuptools wheel
  ```
- **EXPECTED RESULT**: Virtual environment created; `.venv` prompt prefix visible; `pip` updated.
- **FAILURE SYMPTOM**: `ExecutionPolicy` restricted error on Windows; missing `python` binary.
- **TROUBLESHOOTING**: Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in PowerShell before activation.
- **VERIFICATION**: `python -c "import sys; print(sys.prefix)"` points to local `.venv`.

---

## Section B: Dependency Installation & Health Verification

- **PURPOSE**: Install core package in editable mode along with required test dependencies and verify installation.
- **PREREQUISITES**: Virtual environment active (Section A).
- **EXACT COMMAND**:
  ```bash
  pip install -e ".[dev,local]"
  python -m pytest tests/ -q
  ```
- **EXPECTED RESULT**: All 524 core unit and integration tests pass with 0 failures:
  ```text
  524 passed in ~12s
  ```
- **FAILURE SYMPTOM**: `ModuleNotFoundError` or pytest collection errors.
- **TROUBLESHOOTING**: Check `pip list` for `tokenopt`; verify no missing wheels (e.g., `tiktoken`, `fastapi`, `pydantic`).
- **VERIFICATION**: `python -c "import tokenopt; print(tokenopt.__version__)"` outputs `0.1.0`.

---

## Section C: Environment Variable Configuration (Gateway & Proxy)

- **PURPOSE**: Establish baseline environment configuration for Gateway and Enterprise Proxy.
- **PREREQUISITES**: Working shell environment.
- **EXACT COMMAND**:
  ```powershell
  # Windows PowerShell
  $env:JWT_SECRET = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  $env:MAX_OPTIMIZATION_WORKERS = "4"
  $env:FIDELITY_THRESHOLD = "0.995"
  $env:REQUIRE_REAL_FIDELITY = "false"
  $env:OLLAMA_BASE_URL = "http://localhost:11434"
  $env:CORS_ORIGINS = "http://localhost:3000,http://localhost:5173"
  ```
  ```bash
  # Linux / bash
  export JWT_SECRET="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  export MAX_OPTIMIZATION_WORKERS="4"
  export FIDELITY_THRESHOLD="0.995"
  export REQUIRE_REAL_FIDELITY="false"
  export OLLAMA_BASE_URL="http://localhost:11434"
  export CORS_ORIGINS="http://localhost:3000,http://localhost:5173"
  ```
- **EXPECTED RESULT**: Environment variables exported without syntax error.
- **FAILURE SYMPTOM**: Gateway or Proxy warning logs complaining of missing variables.
- **TROUBLESHOOTING**: Ensure `JWT_SECRET` is at least 32 characters; verify variable names match `AppConfig` fields.
- **VERIFICATION**: `python -c "import os; print(len(os.environ['JWT_SECRET']))"` prints `>= 32`.

---

## Section D: JWT Secret Generation and Signing Key Rotation

- **PURPOSE**: Generate cryptographically secure HMAC-SHA256 signing keys and rotate keys safely.
- **PREREQUISITES**: Python standard library `secrets`.
- **EXACT COMMAND**:
  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
- **EXPECTED RESULT**: 64-character hexadecimal string suitable for 256-bit security.
- **FAILURE SYMPTOM**: Using short, guessable passwords triggers startup assertion failure (`JWT_SECRET must be at least 32 bytes`).
- **TROUBLESHOOTING**: In production rotation, issue new tokens with the new key while maintaining support for existing valid tokens during the migration window.
- **VERIFICATION**: `python -c "import os; assert len(bytes.fromhex('<GENERATED_KEY>')) == 32"` succeeds.

---

## Section E: Starting the FastAPI Gateway (tokenopt/server.py)

- **PURPOSE**: Launch the OpenAI-compatible Gateway server.
- **PREREQUISITES**: Port 8000 available; `.venv` active.
- **EXACT COMMAND**:
  ```bash
  python -m uvicorn tokenopt.server:create_app --factory --host 127.0.0.1 --port 8000
  ```
- **EXPECTED RESULT**: Uvicorn running on `http://127.0.0.1:8000`.
- **FAILURE SYMPTOM**: `OSError: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000): address already in use`.
- **TROUBLESHOOTING**: Kill conflicting process on port 8000 (`Get-NetTCPConnection -LocalPort 8000`).
- **VERIFICATION**: Log line: `Application startup complete.`

---

## Section F: Starting the Enterprise Proxy (tokenopt_proxy_v2.py)

- **PURPOSE**: Launch the Enterprise v2 Proxy server with JWT authentication, circuit breakers, and M1.1 concurrency controls.
- **PREREQUISITES**: `JWT_SECRET` configured; port 8001 available.
- **EXACT COMMAND**:
  ```bash
  python -m uvicorn tokenopt_proxy_v2:app --app-dir tokenopt-proxy --host 127.0.0.1 --port 8001
  ```
- **EXPECTED RESULT**: Proxy initializes services and binds to `http://127.0.0.1:8001`.
- **FAILURE SYMPTOM**: Critical log: `JWT_SECRET is not set! Authentication will reject all requests.`
- **TROUBLESHOOTING**: Set `JWT_SECRET` in environment before starting.
- **VERIFICATION**: Log line: `TokenOpt v2.0 fully initialized`.

---

## Section G: Gateway Health & Readiness Verification

- **PURPOSE**: Verify Gateway liveness and readiness probe.
- **PREREQUISITES**: Gateway running on port 8000.
- **EXACT COMMAND**:
  ```bash
  curl -i http://127.0.0.1:8000/health
  ```
- **EXPECTED RESULT**: HTTP 200 with JSON payload:
  ```json
  {"status":"healthy","service":"tokenopt","version":"0.1.0"}
  ```
- **FAILURE SYMPTOM**: Connection refused (`curl: (7) Failed to connect`).
- **TROUBLESHOOTING**: Check if process exited; inspect terminal logs.
- **VERIFICATION**: HTTP status code 200.

---

## Section H: Proxy Health & Readiness Verification

- **PURPOSE**: Verify Enterprise Proxy health status and connected component states.
- **PREREQUISITES**: Proxy running on port 8001.
- **EXACT COMMAND**:
  ```bash
  curl -i http://127.0.0.1:8001/health
  ```
- **EXPECTED RESULT**: HTTP 200 with service health payload.
- **FAILURE SYMPTOM**: HTTP 503 or connection failure.
- **TROUBLESHOOTING**: Inspect logs for failed database or redis connections (if configured in strict mode).
- **VERIFICATION**: JSON response includes `"status": "healthy"`.

---

## Section I: Listing Models & Capabilities

- **PURPOSE**: Query OpenAI-compatible models endpoint from the Gateway.
- **PREREQUISITES**: Gateway active.
- **EXACT COMMAND**:
  ```bash
  curl -s http://127.0.0.1:8000/v1/models
  ```
- **EXPECTED RESULT**: JSON model list:
  ```json
  {
    "object": "list",
    "data": [
      {"id": "llama3.1", "object": "model", "owned_by": "ollama"},
      {"id": "gpt-4o", "object": "model", "owned_by": "openai"},
      {"id": "gpt-4o-mini", "object": "model", "owned_by": "openai"},
      {"id": "claude-3-5-sonnet", "object": "model", "owned_by": "anthropic"}
    ]
  }
  ```
- **FAILURE SYMPTOM**: 404 Not Found.
- **TROUBLESHOOTING**: Check base route URL (must be `/v1/models`).
- **VERIFICATION**: Model IDs present in `data` list.

---

## Section J: Issuing Client JWT Tokens

- **PURPOSE**: Mint signed HS256 JWT tokens for client authentication against Enterprise Proxy.
- **PREREQUISITES**: `pyjwt` installed; `JWT_SECRET` known.
- **EXACT COMMAND**:
  ```bash
  python -c "
  import jwt, time, os
  secret = os.environ.get('JWT_SECRET', '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef')
  payload = {'sub': 'demo_user', 'org': 'enterprise_corp', 'exp': int(time.time()) + 3600}
  print(jwt.encode(payload, secret, algorithm='HS256'))
  "
  ```
- **EXPECTED RESULT**: Base64-encoded three-part JWT token printed to stdout.
- **FAILURE SYMPTOM**: ModuleNotFoundError: No module named 'jwt'.
- **TROUBLESHOOTING**: Ensure `pip install pyjwt` or run in active `.venv`.
- **VERIFICATION**: Token can be decoded with the same secret.

---

## Section K: Executing Chat Completions through Gateway (Ollama Backend)

- **PURPOSE**: Run live end-to-end chat completion through Gateway with optimization pipeline to local Ollama.
- **PREREQUISITES**: Ollama running on `localhost:11434`; model `llama3.1` pulled.
- **EXACT COMMAND**:
  ```bash
  curl -i -X POST http://127.0.0.1:8000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
      "model": "llama3.1",
      "messages": [
        {"role": "system", "content": "You are a helpful assistant. You are a helpful assistant."},
        {"role": "user", "content": "What is the capital of France in one word?   \n\n\n   Answer immediately."}
      ]
    }'
  ```
- **EXPECTED RESULT**: HTTP 200; `choices[0].message.content` contains `"Paris"`; headers include `x-tokenopt-*` telemetry.
- **FAILURE SYMPTOM**: HTTP 502 with `LLM provider error: model 'llama3.1' not found`.
- **TROUBLESHOOTING**: Run `ollama run llama3.1` to pull and test model.
- **VERIFICATION**: Header `x-tokenopt-validation-decision: accept` and `x-tokenopt-tokens-saved > 0`.

---

## Section L: Executing Chat Completions through Proxy (with Auth)

- **PURPOSE**: Route authenticated request through Enterprise Proxy with JWT authentication.
- **PREREQUISITES**: Enterprise Proxy running on port 8001; JWT token minted (Section J).
- **EXACT COMMAND**:
  ```bash
  curl -i -X POST http://127.0.0.1:8001/v1/chat/completions \
    -H "Authorization: Bearer <TOKEN>" \
    -H "Content-Type: application/json" \
    -d '{
      "model": "gpt-4",
      "messages": [
        {"role": "user", "content": "Summarize TokenOpt in one short sentence."}
      ]
    }'
  ```
- **EXPECTED RESULT**: HTTP 200 with completion response; optimization metadata returned in response body or headers.
- **FAILURE SYMPTOM**: HTTP 401 Unauthorized (`{"detail": "Invalid token"}` or `{"detail": "Token expired"}`).
- **TROUBLESHOOTING**: Verify token was signed with the identical `JWT_SECRET` string in Proxy environment.
- **VERIFICATION**: Response body contains `id`, `model`, `choices`, and `usage`.

---

## Section M: Streaming Chat Completions Verification

- **PURPOSE**: Test Server-Sent Events (SSE) streaming mode through the Proxy.
- **PREREQUISITES**: Proxy active; valid JWT token.
- **EXACT COMMAND**:
  ```bash
  curl -N -X POST http://127.0.0.1:8001/v1/chat/completions \
    -H "Authorization: Bearer <TOKEN>" \
    -H "Content-Type: application/json" \
    -d '{
      "model": "gpt-4",
      "stream": true,
      "messages": [
        {"role": "user", "content": "Count from 1 to 5."}
      ]
    }'
  ```
- **EXPECTED RESULT**: Continuous stream of `data: {"choices": [{"delta": {"content": "..."}}]}` chunks ending with `data: [DONE]`.
- **FAILURE SYMPTOM**: 400 Bad Request or abrupt connection close.
- **TROUBLESHOOTING**: Inspect proxy debug logs for SSE chunk parsing errors.
- **VERIFICATION**: Output begins with `data: ` and terminates cleanly with `[DONE]`.

---

## Section N: Content Compression & Headroom Verification

- **PURPOSE**: Verify Headroom structural JSON/content compression on large assistant / tool-result messages.
- **PREREQUISITES**: `headroom` package installed (optional; falls back safely to array sampler if absent).
- **EXACT COMMAND**:
  ```bash
  python -c "
  import json
  from tokenopt.config import TokenOptConfig
  from tokenopt.optimizer import CanonicalOptimizer
  config = TokenOptConfig()
  config.content_compression_enabled = True
  opt = CanonicalOptimizer(config=config)
  msg = [{'role': 'tool', 'content': json.dumps({'items': list(range(200))})}]
  res = opt.optimize(msg, model="gpt-4o")
  print('Original tokens:', res.original_token_count)
  print('Optimized tokens:', res.optimized_token_count)
  print('Compression applied:', res.stage_metrics.get('content_compressor', {}).get('applied', False))
  "
  ```
- **EXPECTED RESULT**: `Optimized tokens < Original tokens`; `Compression applied: True`.
- **FAILURE SYMPTOM**: Optimization fails or errors silently.
- **TROUBLESHOOTING**: Ensure `content_compression_enabled = True`; verify input content exceeds `headroom_min_tokens` threshold (default 100).
- **VERIFICATION**: Reduction in message token count.

---

## Section O: Observing Optimization Telemetry & HTTP Headers

- **PURPOSE**: Inspect optimization telemetry injected by the Gateway on outgoing HTTP responses.
- **PREREQUISITES**: Completed request via Section K.
- **EXACT COMMAND**:
  ```bash
  curl -s -D - -o /dev/null -X POST http://127.0.0.1:8000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{\"model\":\"llama3.1\",\"messages\":[{\"role\":\"user\",\"content\":\"test    prompt   with   spaces\"}]}'
  ```
- **EXPECTED RESULT**: Headers matching:
  ```text
  x-tokenopt-original-tokens: <int>
  x-tokenopt-optimized-tokens: <int>
  x-tokenopt-tokens-saved: <int>
  x-tokenopt-reduction-pct: <float>
  x-tokenopt-pipeline-latency-ms: <float>
  x-tokenopt-validation-decision: accept
  x-tokenopt-rollback-applied: false
  ```
- **FAILURE SYMPTOM**: Missing `x-tokenopt-*` headers.
- **TROUBLESHOOTING**: Ensure request hit `tokenopt.server` and did not encounter early 4xx validation rejection.
- **VERIFICATION**: All diagnostic headers present.

---

## Section P: Concurrency & Load Testing (Simulating Overload / M1.1)

- **PURPOSE**: Prove M1.1 concurrency guarantees: bounded executor, bounded semaphore, and fast HTTP 503 upon capacity exhaustion.
- **PREREQUISITES**: Proxy active with `MAX_OPTIMIZATION_WORKERS=2`.
- **EXACT COMMAND**:
  ```bash
  python -c "
  import asyncio, aiohttp, time
  async def main():
      async with aiohttp.ClientSession() as s:
          tasks = [
              s.post('http://127.0.0.1:8001/v1/chat/completions',
                     headers={'Authorization': 'Bearer <TOKEN>'},
                     json={'model': 'gpt-4', 'messages': [{'role': 'user', 'content': 'long prompt ' * 50}]})
              for _ in range(10)
          ]
          resps = await asyncio.gather(*tasks)
          print('Statuses:', [r.status for r in resps])
  asyncio.run(main())
  "
  ```
- **EXPECTED RESULT**: 200s for admitted workers, HTTP 503 `Optimization capacity exhausted. Please retry later.` for excess load.
- **FAILURE SYMPTOM**: Server hangs or memory balloons unbounded.
- **TROUBLESHOOTING**: Inspect `MAX_OPTIMIZATION_WORKERS` in `AppConfig`; ensure semaphore timeout is configured (0.1s).
- **VERIFICATION**: Non-admitted requests receive 503 with `Retry-After: 1`.

---

## Section Q: Circuit Breaker Testing & Fallback Verification

- **PURPOSE**: Verify provider circuit breaker trips after consecutive failures and transitions through CLOSED -> OPEN -> HALF-OPEN states.
- **PREREQUISITES**: `provider_client_v2.py` with mock failing provider.
- **EXACT COMMAND**:
  ```bash
  python -m pytest tokenopt-proxy/tests/test_circuit_breaker.py -v
  ```
- **EXPECTED RESULT**: All 5 circuit breaker tests pass:
  ```text
  test_circuit_breaker_initial_state PASSED
  test_circuit_breaker_trips_after_threshold PASSED
  test_circuit_breaker_half_open_transition PASSED
  test_circuit_breaker_recovers_on_success PASSED
  test_circuit_breaker_reopens_on_half_open_failure PASSED
  ```
- **FAILURE SYMPTOM**: Tests fail or hang.
- **TROUBLESHOOTING**: Inspect `failure_threshold` (default 5) and `recovery_timeout` (default 30.0s).
- **VERIFICATION**: Circuit breaker raises `CircuitBreakerOpenError` while OPEN.

---

## Section R: Fidelity Validator Configuration & Degraded Mode

- **PURPOSE**: Configure response/prompt fidelity validation and verify behavior under missing embedding models.
- **PREREQUISITES**: Proxy environment variables.
- **EXACT COMMAND**:
  ```bash
  python -c "
  from tokenopt.compat import DegradedFidelityValidator
  val = DegradedFidelityValidator()
  print('Validator initialized:', val.__class__.__name__)
  "
  ```
- **EXPECTED RESULT**: `DegradedFidelityValidator` fails open safely (score 1.0) when `REQUIRE_REAL_FIDELITY=false`.
- **FAILURE SYMPTOM**: RuntimeError on startup if `REQUIRE_REAL_FIDELITY=true` without `sentence-transformers` or `OPENAI_API_KEY`.
- **TROUBLESHOOTING**: Install `sentence-transformers` for production or set `REQUIRE_REAL_FIDELITY=false` for dev/demo.
- **VERIFICATION**: `test_degradation.py` passes 8/8 tests.

---

## Section S: PostgreSQL Audit Logging Configuration & Verification

- **PURPOSE**: Enable and verify persistent audit trail of prompts, token savings, latency, and costs.
- **PREREQUISITES**: PostgreSQL database instance running.
- **EXACT COMMAND**:
  ```bash
  python -c "
  import asyncio
  from persistence_layer_v2 import AuditDatabase
  async def check():
      db = AuditDatabase(dsn='postgresql://postgres:postgres@localhost:5432/tokenopt', retention_days=90)
      # Connect and verify table schema creation
      await db.initialize()
      print('Audit DB initialized successfully')
      await db.close()
  asyncio.run(check())
  "
  ```
- **EXPECTED RESULT**: Database connects and creates `audit_log` table with indexes.
- **FAILURE SYMPTOM**: `asyncpg.exceptions.ConnectionDoesNotExistError` or auth failure.
- **TROUBLESHOOTING**: Check credentials in `POSTGRES_DSN`; verify PostgreSQL service is active.
- **VERIFICATION**: `SELECT count(*) FROM audit_log;` returns integer count.

---

## Section T: Redis Distributed Cache Configuration & Verification

- **PURPOSE**: Enable and verify cross-instance semantic and exact prompt response caching.
- **PREREQUISITES**: Redis server running on `localhost:6379`.
- **EXACT COMMAND**:
  ```bash
  python -c "
  import asyncio
  from persistence_layer_v2 import DistributedCache
  async def check():
      cache = DistributedCache(redis_url='redis://localhost:6379/0', ttl_seconds=3600)
      await cache.initialize()
      print('Redis cache initialized successfully')
      await cache.close()
  asyncio.run(check())
  "
  ```
- **EXPECTED RESULT**: Connection established; cache ready.
- **FAILURE SYMPTOM**: Warning in logs: `redis not installed. Redis features disabled.` or connection refused.
- **TROUBLESHOOTING**: Install `redis` (`pip install redis`); start redis server (`redis-server`).
- **VERIFICATION**: `test_cache.py` passes 5/5 tests.

---

## Section U: Kafka Event Streaming Configuration & Verification

- **PURPOSE**: Stream optimization audit events to enterprise message bus for real-time analytics.
- **PREREQUISITES**: Apache Kafka brokers reachable on port 9092.
- **EXACT COMMAND**:
  ```bash
  python -c "
  import asyncio
  from persistence_layer_v2 import EventStreamer
  async def check():
      streamer = EventStreamer(bootstrap_servers='localhost:9092')
      await streamer.initialize()
      print('Kafka streamer initialized successfully')
      await streamer.close()
  asyncio.run(check())
  "
  ```
- **EXPECTED RESULT**: Kafka producer connects; events stream to `tokenopt-events` topic.
- **FAILURE SYMPTOM**: `KafkaConnectionError` in logs.
- **TROUBLESHOOTING**: Verify broker addresses in `KAFKA_BROKERS`; ensure topic auto-creation is enabled.
- **VERIFICATION**: Event streamer logs `Kafka producer started`.

---

## Section V: Docker Container Build & Local Run

- **PURPOSE**: Containerize TokenOpt Enterprise Proxy for cloud orchestration (Kubernetes / ECS).
- **PREREQUISITES**: Docker engine active.
- **EXACT COMMAND**:
  ```bash
  docker build -t tokenopt-proxy:latest -f tokenopt-proxy/Dockerfile tokenopt-proxy/
  docker run -d --name tokenopt -p 8000:8000 -e JWT_SECRET="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef" tokenopt-proxy:latest
  ```
- **EXPECTED RESULT**: Container builds cleanly and runs in background.
- **FAILURE SYMPTOM**: Build error on pip install or missing dependencies.
- **TROUBLESHOOTING**: Inspect `docker logs tokenopt` for startup exceptions.
- **VERIFICATION**: `curl http://localhost:8000/health` returns HTTP 200.

---

## Section W: Failure Recovery: Provider Outage / 502 Bad Gateway

- **PURPOSE**: Diagnose and recover when upstream LLM provider is down or returning errors.
- **PREREQUISITES**: Gateway or Proxy receiving 502/503 from provider.
- **EXACT COMMAND**:
  ```bash
  # Check provider connectivity
  curl -s -o /dev/null -w "%{http_code}" http://localhost:11434/api/tags
  # Or test cloud provider directly
  curl -s -o /dev/null -w "%{http_code}" https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"
  ```
- **EXPECTED RESULT**: Upstream returns 200 OK. If non-200, upstream outage is confirmed.
- **FAILURE SYMPTOM**: Clients receive HTTP 502 `LLM provider error: ...`.
- **TROUBLESHOOTING**:
  1. If local Ollama: restart with `ollama serve`.
  2. If cloud provider: failover to secondary provider by adjusting priority in `ProviderConfig` or updating routing rules in `config.routing_rules`.
- **VERIFICATION**: Re-run Section K; verify 200 OK response.

---

## Section X: Failure Recovery: Auth Failure / 401 Unauthorized

- **PURPOSE**: Diagnose and resolve authentication rejections.
- **PREREQUISITES**: Request failing with HTTP 401.
- **EXACT COMMAND**:
  ```bash
  python -c "
  import jwt, os
  token = '<TOKEN_UNDER_INVESTIGATION>'
  secret = os.environ.get('JWT_SECRET', '')
  try:
      decoded = jwt.decode(token, secret, algorithms=['HS256'])
      print('Token is VALID:', decoded)
  except jwt.ExpiredSignatureError:
      print('ERROR: Token has EXPIRED')
  except jwt.InvalidSignatureError:
      print('ERROR: Invalid signature (JWT_SECRET mismatch)')
  except Exception as e:
      print('ERROR:', e)
  "
  ```
- **EXPECTED RESULT**: Script prints exact root cause (expired, signature mismatch, or malformed).
- **FAILURE SYMPTOM**: Client receives `{"detail": "Not authenticated"}` or `{"detail": "Token expired"}`.
- **TROUBLESHOOTING**: Issue fresh token per Section J using matching `JWT_SECRET`.
- **VERIFICATION**: Client request succeeds with 200 OK.

---

## Section Y: Failure Recovery: Worker Exhaustion / 503 Capacity Limit

- **PURPOSE**: Handle and mitigate high-concurrency throttling under sudden traffic spikes.
- **PREREQUISITES**: Proxy returning HTTP 503 with detail `Optimization capacity exhausted. Please retry later.`
- **EXACT COMMAND**:
  ```bash
  # Scale worker pool dynamically or horizontally
  export MAX_OPTIMIZATION_WORKERS="8"
  # Or restart proxy instance with higher worker ceiling
  ```
- **EXPECTED RESULT**: Worker pool sized appropriately to handle expected burst concurrency.
- **FAILURE SYMPTOM**: 503 responses under heavy load.
- **TROUBLESHOOTING**:
  1. Instruct clients to respect `Retry-After: 1` header.
  2. Increase `MAX_OPTIMIZATION_WORKERS` to match available CPU cores.
  3. Deploy additional container replicas behind a round-robin load balancer.
- **VERIFICATION**: Re-run concurrency script; observe 0 rejected requests.

---

## Section Z: Graceful Shutdown & Maintenance Mode Procedure

- **PURPOSE**: Terminate TokenOpt instances cleanly without dropping in-flight LLM requests or corrupting audit logs.
- **PREREQUISITES**: Running Gateway or Proxy process.
- **EXACT COMMAND**:
  ```bash
  # Send SIGTERM (or Ctrl+C in console)
  kill -SIGTERM <PID>
  ```
- **EXPECTED RESULT**: Server stops accepting new connections, drains in-flight requests within timeout, closes provider sessions, flushes audit DB, and exits with code 0:
  ```text
  INFO: Shutting down TokenOpt v2.0...
  INFO: Waiting for background tasks to complete...
  INFO: Application shutdown complete.
  ```
- **FAILURE SYMPTOM**: Hard kill (SIGKILL) leaves zombie connections or half-written audit batches.
- **TROUBLESHOOTING**: Always allow Uvicorn grace period (`--timeout-graceful-shutdown 30`).
- **VERIFICATION**: Process exits with code 0; port becomes unbound immediately.
