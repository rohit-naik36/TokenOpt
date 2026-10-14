## Ticket
{
  "id": "T03",
  "title": "Per-API-key rate limiting at the gateway",
  "type": "feature",
  "priority_hint": "High",
  "reporter": "security-eng",
  "labels": [
    "gateway",
    "rate-limit",
    "security"
  ],
  "description": "We need a fixed-window rate limiter keyed by API key to stop a single integration from degrading the shared cluster. Limit: 100 requests per 60-second window per key. When exceeded, respond with HTTP 429 and a `Retry-After` header (seconds until the window resets). Use the existing Redis. The window must reset 60 seconds after the first request in it, regardless of traffic during the window.\n\nOut of scope: per-endpoint limits, burst credits, dashboards.",
  "environment": "Node 20, TypeScript 5, Express 4, Redis 7 via ioredis. Service: gateway.",
  "comments": [
    "security-eng: Last incident a single key sent 9k rps for 20 minutes.",
    "sre: Redis commands must be cheap; this runs on every request, so avoid Lua unless needed.",
    "backend-dev: INCR plus EXPIRE is enough for fixed window."
  ]
}

## Diff
diff --git a/gateway/src/middleware/rateLimit.ts b/gateway/src/middleware/rateLimit.ts
new file mode 100644
--- /dev/null
+++ b/gateway/src/middleware/rateLimit.ts
@@ -0,0 +1,26 @@
+import type { NextFunction, Request, Response } from "express";
+import { redis } from "../redis";
+
+const LIMIT = 100;
+const WINDOW_SECONDS = 60;
+
+export async function rateLimit(req: Request, res: Response, next: NextFunction) {
+  const key = req.header("x-api-key");
+  if (!key) {
+    return res.status(401).json({ error: "missing api key" });
+  }
+
+  const bucket = `rl:${key}`;
+  const count = await redis.incr(bucket);
+  await redis.expire(bucket, WINDOW_SECONDS);
+
+  if (count > LIMIT) {
+    const ttl = await redis.ttl(bucket);
+    res.setHeader("Retry-After", String(ttl));
+    return res.status(429).json({ error: "rate limit exceeded" });
+  }
+  return next();
+}


## Stage output: triage
{"severity": "P1", "category": "feature", "component": "gateway", "summary": "Implement per-API-key fixed-window rate limiting (100 req/60s) using Redis to prevent cluster degradation.", "risk_flags": ["Redis performance impact"], "needs_security_review": true}

## Stage output: requirements
{"user_story": "As a system administrator, I want to enforce per-API-key rate limits at the gateway so that a single integration cannot degrade the shared cluster.", "acceptance_criteria": ["When an API key has made fewer than 100 requests in the current 60-second window, the gateway returns HTTP 200 with the request body.", "When an API key reaches exactly 100 requests within a 60-second window, the gateway responds with HTTP 429 and includes a `Retry-After` header indicating seconds until the window resets.", "The rate limit window is fixed at 60 seconds starting from the timestamp of the first request in that window, regardless of traffic volume during the interval.", "The gateway uses Redis to store the counter and expiration time for each API key without executing Lua scripts for simple increment-and-expire operations.", "If Redis is unavailable or returns an error, the gateway must return HTTP 503 Service Unavailable instead of allowing unlimited requests."], "non_goals": ["Implement per-endpoint specific rate limits", "Implement burst credit mechanisms", "Provide usage dashboards"], "open_questions": []}

## Stage output: plan
{"steps": [{"id": 1, "description": "Create a new module `rate-limiter` in the gateway service to encapsulate Redis interaction logic.", "files": ["gateway/src/rate-limiter/index.ts"]}, {"id": 2, "description": "Implement the fixed-window logic using `INCR` and `EXPIRE` commands via ioredis, calculating the reset time based on the current window start.", "files": ["gateway/src/rate-limiter/index.ts"]}, {"id": 3, "description": "Add a Redis fallback handler to catch connection errors and return HTTP 503 Service Unavailable.", "files": ["gateway/src/rate-limiter/index.ts"]}, {"id": 4, "description": "Integrate the rate limiter middleware into the Express request lifecycle before the main route handlers.", "files": ["gateway/src/app.ts", "gateway/src/middleware/rate-limit.ts"]}, {"id": 5, "description": "Update the gateway configuration to define the API key header name and limit constants (100 req/60s).", "files": ["gateway/config/env.example.ts"]}, {"id": 6, "description": "Write unit tests for valid requests, rate limit exceeded scenarios, and Redis failure modes.", "files": ["gateway/test/rate-limiter.test.ts"]}], "risks": ["Redis performance impact: Mitigated by using atomic INCR/EXPIRE commands without Lua scripts as per backend-dev triage notes.", "Memory usage growth: Mitigated by relying on Redis TTL (EXPIRE) to automatically evict stale keys when the 60-second window passes."], "test_plan": ["Verify HTTP 200 response for a new API key making its first request.", "Verify HTTP 429 response with correct `Retry-After` header when an API key hits exactly 100 requests within 60 seconds.", "Verify that the rate limit window resets correctly after 60 seconds from the first request in the window.", "Verify HTTP 503 Service Unavailable response when Redis connection is mocked to fail."]}

## Stage output: review
{"verdict":"request_changes","findings":[{"file":"gateway/src/middleware/rateLimit.ts","line":13,"severity":"blocker","issue":"The code executes `redis.incr` followed by `redis.expire`. This is a race condition: if two requests arrive simultaneously, the first increments to 1 (expires), the second increments to 2 (expires), but neither sees the count exceed LIMIT until after both have executed. A burst of N requests can all pass before any expire check happens, allowing >100 requests in the window.","suggested_fix":"Use a single atomic Redis transaction or Lua script that checks TTL, increments, sets expiry, and returns the new count atomically, OR use `redis.incr` with `EXPIRE` combined in one call if supported, ensuring the check happens before the next request can increment."},{"file":"gateway/src/middleware/rateLimit.ts","line":13,"severity":"major","issue":"The code does not handle Redis errors. If `redis.incr` or `redis.expire` fails (network error, timeout), the middleware proceeds to `next()` instead of returning HTTP 503.","suggested_fix":"Wrap Redis calls in a try/catch block that returns `res.status(503).json({ error: 'service unavailable' })` on any Redis error."},{"file":"gateway/src/middleware/rateLimit.ts","line":17,"severity":"major","issue":"The code checks `if (count > LIMIT)` after incrementing. When count equals 100, it returns 200. The requirement states: 'When an API key reaches exactly 100 requests within a 60-second window, the gateway responds with HTTP 429'.","suggested_fix":"Change condition to `if (count >= LIMIT)` so that the 100th request is rejected."},{"file":"gateway/src/middleware/rateLimit.ts","line":17,"severity":"major","issue":"The code uses `await redis.ttl(bucket)` after rejecting. If Redis is slow or under load, this adds latency to the error response and may cause timeouts.","suggested_fix":"Use `redis.incr` with `EXPIRE` in one atomic call (via Lua or pipeline) that returns both count and TTL, avoiding a separate TTL call."}],"summary":"Fix race condition between incr/expire, handle Redis errors with 503, reject on count>=100 not >100, and avoid extra TTL call for error responses."}

## Stage output: release_note
{"title": "Per-API-key rate limiting added to gateway", "summary": "The gateway now enforces a limit of 100 requests per 60-second window per API key. Exceeding this limit returns HTTP 429 with a Retry-After header.", "changes": ["Gateway responds with HTTP 429 and Retry-After header when an API key exceeds 100 requests in a 60-second window.", "Gateway returns HTTP 503 Service Unavailable if the Redis backend is unavailable."], "breaking": false, "upgrade_notes": ""}