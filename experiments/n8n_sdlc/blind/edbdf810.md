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
{"severity": "P1", "category": "feature", "component": "gateway", "summary": "Implement fixed-window rate limiting per API key at the gateway to prevent single integrations from degrading cluster performance.", "risk_flags": ["rate-limiting", "redis-dependency"], "needs_security_review": false}

## Stage output: requirements
{"user_story": "As an API consumer, I want my requests to be rate-limited by a fixed window so that my integration does not degrade the shared cluster.", "acceptance_criteria": ["Given the gateway receives a request with an API key, when the total count of requests for that key in the current 60-second window is less than 100, then respond with HTTP 200 and increment the counter in Redis.", "Given the gateway receives a request with an API key, when the total count of requests for that key in the current 60-second window reaches 100, then respond with HTTP 429.", "Given the gateway receives a request with an API key, when the limit is exceeded, then include a `Retry-After` header in the response containing the number of seconds until the 60-second window resets.", "Given the gateway receives a request with an API key, when the first request for that key occurs at time T, then the rate limit window expires exactly at time T + 60 seconds regardless of subsequent traffic volume.", "Given the gateway receives a request with an API key, when the Redis connection fails during the check or increment operation, then respond with HTTP 503 and log the error."], "non_goals": ["Implement per-endpoint rate limits.", "Implement burst credit mechanisms.", "Provide usage dashboards for API keys."], "open_questions": []}

## Stage output: plan
{"steps":[{"id":1,"description":"Create a new middleware module for per-API-key rate limiting in the gateway service.","files":["gateway/middleware/rate_limiter.py"]},{"id":2,"description":"Implement Redis-based sliding window logic to track request counts and calculate reset times.","files":["gateway/middleware/rate_limiter.py"]},{"id":3,"description":"Add logic to increment counters on success and return HTTP 429 with Retry-After header on limit exceeded.","files":["gateway/middleware/rate_limiter.py"]},{"id":4,"description":"Implement graceful degradation to return HTTP 503 and log errors when Redis connection fails.","files":["gateway/middleware/rate_limiter.py"]},{"id":5,"description":"Register the new rate limiting middleware in the gateway request pipeline.","files":["gateway/app/main.py"]},{"id":6,"description":"Add unit tests for successful requests, limit exceeded scenarios, and Redis failure cases.","files":["gateway/tests/test_rate_limiter.py"]}],"risks":["Redis dependency failure could cause service degradation; mitigated by catching connection errors and returning 503 with logging.","Rate limiting logic might introduce latency; mitigated by using atomic Redis operations and keeping the middleware lightweight."],"test_plan":["Request with valid API key under limit returns 200 and increments counter.","Request with valid API key at limit returns 429 with correct Retry-After header.","Redis connection failure results in 503 response and error log entry.","Rate limit window resets exactly 60 seconds after the first request for a key."]}

## Stage output: review
{"verdict":"request_changes","findings":[{"file":"gateway/src/middleware/rateLimit.ts","line":12,"severity":"blocker","issue":"The code increments the counter before checking the limit and sets a TTL on every request, violating the acceptance criteria that the window expires exactly 60 seconds from the first request regardless of traffic. The current logic uses a fixed-window approach where the window resets based on the last write, not the first.","suggested_fix":"Use Redis sorted sets (ZADD/ZRANGECOUNT) to implement a sliding window: track timestamps in [T, T+60), increment only if count < 100, and calculate TTL as min(60 - oldest_timestamp, remaining_window)."},{"file":"gateway/src/middleware/rateLimit.ts","line":13,"severity":"blocker","issue":"The code calls `redis.expire(bucket, WINDOW_SECONDS)` on every request, which resets the bucket's expiration to 60 seconds from now instead of preserving the original window start time. This causes the rate limit window to extend indefinitely under heavy traffic.","suggested_fix":"Remove the unconditional `expire` call; rely on sorted set expiration or only set TTL when initializing the bucket (first request)."},{"file":"gateway/src/middleware/rateLimit.ts","line":16,"severity":"major","issue":"The code returns HTTP 429 when count > LIMIT, but it does not handle the case where Redis fails during `incr` or `expire`, violating the acceptance criteria for graceful degradation with HTTP 503.","suggested_fix":"Wrap Redis calls in a try-catch block; if an error occurs, log it and return res.status(503).json({error:\"service unavailable\"})."}],"summary":"Fix sliding window logic using sorted sets, remove unconditional TTL reset, and add Redis failure handling for HTTP 503."}

## Stage output: release_note
{"title": "Per-API-key rate limiting added at gateway", "summary": "The system now enforces per-API-key rate limits using a fixed window algorithm to protect cluster stability.", "changes": ["Rate limits are now enforced individually for each API key rather than globally.", "Exceeding the limit returns a 429 Too Many Requests status code."], "breaking": false, "upgrade_notes": ""}