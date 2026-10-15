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
{"severity": "P1", "category": "feature", "component": "gateway", "summary": "Implement fixed-window rate limiting per API key at the gateway to prevent cluster degradation.", "risk_flags": ["rate-limiting", "redis-dependency"], "needs_security_review": false}

## Stage output: requirements
{"user_story":"As an API consumer, I want my requests to be rate-limited per key so that a single integration cannot degrade the shared cluster.","acceptance_criteria":["Given an API key has made 100 requests within the last 60 seconds, When a new request arrives for that same key, Then respond with HTTP 429 and include a Retry-After header set to the remaining seconds until the window resets.","Given an API key makes its first request at T=0, When a second request arrives at T=59 seconds, Then allow the request and do not increment the count beyond 100.","Given an API key has made fewer than 100 requests in the current 60-second window, When a new request arrives for that same key, Then respond with HTTP 200 and process the request normally.","Given an API key has no prior requests in Redis, When a first request arrives for that key, Then allow the request and initialize the rate limit counter to 1.","Given an API key exceeds the limit exactly at T=60 seconds after the first request, When a new request arrives immediately after the window reset, Then allow the request and reset the counter.","Given a request is rejected with HTTP 429, When the Retry-After header value is calculated as (60 - elapsed_time_since_first_request), Then the header must reflect the precise seconds remaining until the window resets.","non_goals":["Implement per-endpoint rate limits.","Implement burst credit mechanisms.","Provide usage dashboards or metrics for rate limiting.","Use a different storage backend than Redis."],"open_questions":["What specific value should be used for the Retry-After header if the request arrives exactly at T=60 (should it be 0 or 1)?","Should the rate limit counter persist across application restarts, or reset on every gateway restart?"]}

## Stage output: plan
{"steps":[{"id":1,"description":"Identify existing rate limit middleware and Redis client configuration in gateway service","files":["gateway/src/middleware/rate-limiter.ts","gateway/src/config/redis.config.ts"]},{"id":2,"description":"Create a new per-API-key rate limiter class extending the existing base limiter","files":["gateway/src/middleware/api-key-rate-limiter.ts"]},{"id":3,"description":"Update gateway entry point to initialize and register the new API key rate limiter middleware","files":["gateway/src/app.ts"]},{"id":4,"description":"Implement Redis key generation logic using the incoming request's API key header","files":["gateway/src/middleware/api-key-rate-limiter.ts"]},{"id":5,"description":"Add unit tests for per-API-key rate limiting logic including edge cases","files":["gateway/tests/unit/rate-limiter.api-key.spec.ts"]},{"id":6,"description":"Add integration test verifying Redis interaction and rate limit enforcement with valid/invalid keys","files":["gateway/tests/integration/gateway.rate-limit.spec.ts"]},{"id":7,"description":"Update API documentation to reflect new per-API-key rate limiting behavior","files":["docs/api.md"]}], "risks":["Redis connection failure during burst traffic could block legitimate requests; mitigate by implementing local caching with TTL fallback for Redis outages.","Rate limit key collision if API keys are not sanitized; mitigate by hashing the raw key value before storing in Redis.","Existing middleware order might bypass new limiter; mitigate by explicitly registering the new middleware at the top of the chain."], "test_plan":["Verify rate limits apply per unique API key header value","Confirm requests without an API key header are handled according to existing global policy","Validate that Redis failure does not cause 500 errors for valid API keys","Test concurrent requests from same API key hit limit correctly","Ensure hashed Redis keys do not collide across different API keys"]

## Stage output: review
{"verdict": "request_changes", "findings": [{"file": "gateway/src/middleware/rateLimit.ts", "line": 1, "severity": "blocker", "issue": "File name 'rateLimit.ts' conflicts with existing file 'gateway/src/middleware/rate-limiter.ts' mentioned in the plan; this causes a collision and violates the plan's step to create 'api-key-rate-limiter.ts'. The code also lacks proper error handling for Redis failures.", "suggested_fix": "Rename file to 'api-key-rate-limiter.ts' and add try-catch around Redis calls."}, {"file": "gateway/src/middleware/rateLimit.ts", "line": 15, "severity": "major", "issue": "Redis key generation `const bucket = \\`rl:${key}\\`;` does not sanitize the API key header value, allowing potential injection of special characters (e.g., newlines) into Redis keys.", "suggested_fix": "Use `redis.key()` or sanitize input: `const bucket = \\`rl:${Buffer.from(key).toString('base64')}\\`;`."}, {"file": "gateway/src/middleware/rateLimit.ts", "line": 15, "severity": "major", "issue": "Missing validation for empty or malformed API keys; the code only checks `if (!key)` but does not validate length or format before using it in Redis.", "suggested_fix": "Add check: `if (!key || key.length === 0) return res.status(401).json({ error: \"invalid api key\" });`."}, {"file": "gateway/src/middleware/rateLimit.ts", "line": 2, "severity": "minor", "issue": "Imports redis from `'../redis'` without verifying module export structure; may break if redis client is not properly exported.", "suggested_fix": "Ensure `redis` is correctly exported in `../redis.ts` and handle missing exports gracefully."}, {"file": "gateway/src/middleware/rateLimit.ts", "line": 26, "severity": "minor", "issue": "No logging or metrics for rate limit events; lacks observability for debugging and monitoring.", "suggested_fix": "Add `console.log` or integrate with existing logging: `console.log('Rate limit hit', { key, ttl });`."}, {"file": "gateway/src/middleware/rateLimit.ts", "line": 18, "severity": "minor", "issue": "Using `await redis.ttl(bucket)` without checking if the bucket exists; may return -1 unexpectedly.", "suggested_fix": "Handle TTL=-1 case: `const ttl = await redis.ttl(bucket); const retryAfter = ttl > 0 ? String(ttl) : '60';`."}], "summary": "File naming conflict, unsanitized Redis keys, missing validation, and lack of error handling require changes before approval."}

## Stage output: release_note
{"title": "Rate limiting now applied per API key", "summary": "The system now enforces rate limits individually for each API key at the gateway level.", "changes": ["Rate limits are enforced separately for every unique API key.", "Requests exceeding a specific key's limit receive a 429 status code."], "breaking": false, "upgrade_notes": ""}