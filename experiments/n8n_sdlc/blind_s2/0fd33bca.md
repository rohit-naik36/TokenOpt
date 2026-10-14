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
{"severity": "P2", "category": "feature", "component": "api", "summary": "Add a fixed-window, per-API-key rate limiter at the gateway (100 requests per 60s, HTTP 429 with Retry-After) backed by existing Redis, to protect the shared cluster from a single noisy integration.", "risk_flags": ["Gateway change affects all API traffic", "Redis dependency on request path", "Behavior on Redis outage unspecified", "Requires API key identification at the gateway", "Reporter priority hint High not justified by a stated outage or deadline"], "needs_security_review": true}

## Stage output: requirements
{"user_story": "As a platform operator, I want the API gateway to limit each API key to 100 requests per 60-second fixed window so that a single integration cannot degrade the shared cluster for other clients", "acceptance_criteria": ["Given an API key that has made fewer than 100 requests in its current 60-second window, when it sends a request, then the gateway forwards the request to the upstream service and the response status is not 429.", "Given an API key that has already made 100 requests in its current 60-second window, when it sends an additional request, then the gateway responds with HTTP 429 and does not forward the request upstream.", "Given the gateway has returned HTTP 429 to an API key, when the response is sent, then it includes a `Retry-After` header whose integer value equals the number of seconds remaining until that key's window resets, and that value is between 1 and 60 inclusive.", "Given an API key whose window started at time T, when 60 seconds have elapsed since T regardless of how many requests arrived in between, then the next request from that key is counted in a new window starting at its own arrival time and is allowed.", "Given two different API keys each sending requests, when one key exceeds 100 requests in a window, then the other key's request count and allowance are unaffected."], "non_goals": ["Per-endpoint or per-route rate limits", "Burst credits or token-bucket / sliding-window algorithms", "Dashboards, metrics visualisation or alerting configuration", "Changes to the rate limit values per customer tier"], "open_questions": ["What should the gateway do with requests that carry no API key or an unrecognised key: reject them, skip rate limiting, or apply a default limit?", "If Redis is unavailable, should the gateway fail open (allow traffic) or fail closed (reject traffic)?", "Should the 429 response body follow a specific error format used elsewhere in the API?", "Should rate-limit decisions be logged per request, and if so at what level?"]}

## Stage output: plan
{"steps": [{"id": 1, "description": "Confirm how the gateway currently extracts and validates the API key from incoming requests and identify the single request-handling hook where a pre-forward check can be inserted.", "files": ["api/gateway/middleware", "api/gateway/auth"]}, {"id": 2, "description": "Add a fixed-window rate limiter module that, for a given API key, atomically increments a counter keyed to a window starting at the key's first request in a new window, sets the counter expiry to 60 seconds, and returns the count together with the seconds remaining in the window.", "files": ["api/gateway/ratelimit"]}, {"id": 3, "description": "Wire the rate limiter into the request pipeline so that requests exceeding 100 in the current window receive an HTTP 429 response with a Retry-After header set to the remaining window seconds (clamped to 1 through 60), and such requests are not forwarded upstream; requests at or under the limit proceed unchanged.", "files": ["api/gateway/middleware", "api/gateway/ratelimit"]}, {"id": 4, "description": "Load the limit (100) and window (60 seconds) from existing configuration, with defaults matching the ticket, and document the chosen behavior for Redis unavailability (fail open or fail closed) explicitly in code and configuration.", "files": ["api/config", "api/gateway/ratelimit"]}, {"id": 5, "description": "Add unit and integration tests covering each acceptance criterion, including window reset, per-key isolation, and Retry-After bounds, then run the full API test suite to confirm no regressions in existing gateway routes.", "files": ["api/tests/gateway", "api/tests/ratelimit"]}], "risks": ["Gateway change affects all API traffic: roll out behind a configuration flag defaulting to disabled, and enable first in staging with traffic replay before production.", "Redis dependency on the request path adds latency and a failure point: use a single round trip per request (INCR with EXPIRE set on first increment) and set a short client timeout so slow Redis does not stall requests.", "Behavior on Redis outage is unspecified: confirm the intended policy with the ticket owner before implementation; until confirmed, default to fail open with logging and a metric so outages are visible without blocking traffic.", "Fixed-window boundary bursts allow up to roughly 200 requests across a window edge: this matches the ticket's stated semantics, so note it in the PR description rather than introducing a sliding window.", "Clock skew across gateway instances can make Retry-After inconsistent: derive remaining seconds from the Redis key TTL rather than local clocks, and rely on the clamp to 1 through 60 for edge cases.", "The reporter's High priority is not backed by a stated outage or deadline: confirm urgency with the requester during review, but do not skip the staging rollout to meet an unstated date."], "test_plan": ["Key with fewer than 100 requests in a window receives its request forwarded upstream with a non-429 status (criterion 1).", "Key at exactly 100 requests receives its 100th request forwarded, and the 101st request receives HTTP 429 without any upstream call being made (criterion 2).", "A 429 response includes an integer Retry-After header equal to the seconds remaining in the window, and the value is between 1 and 60 inclusive, including at the very start and very end of a window (criterion 3).", "After 60 seconds elapse from window start, a key that previously hit the limit is allowed again, and its next request starts a new window at its arrival time, even if many requests arrived during the prior window (criterion 4).", "Two keys operate independently: one key exceeding 100 requests does not change the count or allowance of the other key, verified with interleaved requests (criterion 5).", "Redis unavailable: the configured fail-open or fail-closed policy is applied, the outage is logged, and the metric is emitted, with no unhandled exception reaching the client.", "Regression: existing gateway routes and authentication behavior are unchanged for requests under the limit and when the feature flag is disabled."]}

## Stage output: review
{"verdict": "request_changes", "findings": [{"file": "gateway/src/middleware/rateLimit.ts", "line": 13, "severity": "blocker", "issue": "`await redis.expire(bucket, WINDOW_SECONDS);` is executed on every request, so the TTL is refreshed on each call. A steady client sending a request at least once every 60 seconds never gets a reset, violating the criterion that the next request after 60 seconds from the window start begins a new window. The window should only be set when the counter is first created (`count === 1`).", "suggested_fix": "Only set the expiry when the key is created: `const count = await redis.incr(bucket); if (count === 1) await redis.expire(bucket, WINDOW_SECONDS);`, or use a single atomic Lua script / `SET key 0 EX 60 NX` followed by `INCR` so the expiry cannot be lost between commands."}, {"file": "gateway/src/middleware/rateLimit.ts", "line": 11, "severity": "major", "issue": "The `incr` and `expire` calls are two separate round trips and not atomic. If the process crashes between them, the key persists with no TTL and that API key is permanently rate-limited.", "suggested_fix": "Use a Lua script or a MULTI/EXEC transaction that performs INCR and conditionally sets EXPIRE together, or use `SET ... EX 60 NX` then `INCR`."}, {"file": "gateway/src/middleware/rateLimit.ts", "line": 17, "severity": "major", "issue": "`const ttl = await redis.ttl(bucket); res.setHeader(\"Retry-After\", String(ttl));` does not clamp to the 1..60 range required by the acceptance criteria. If the key has no TTL, `ttl` returns -1 (invalid header value); if it is 0 or otherwise out of range, the header is invalid.", "suggested_fix": "Clamp the value: `const retryAfter = Math.min(WINDOW_SECONDS, Math.max(1, ttl));` and set `Retry-After` to `String(retryAfter)`."}, {"file": "gateway/src/middleware/rateLimit.ts", "line": 6, "severity": "major", "issue": "The Redis failure path is unhandled: if `redis.incr` rejects, the async middleware throws and the request either hangs or produces an unhandled error. The plan requires an explicit fail-open or fail-closed decision, which is absent.", "suggested_fix": "Wrap the Redis calls in try/catch and explicitly choose the behavior (e.g., log and call `next()` to fail open, or return 503 to fail closed), documenting the choice in code and config."}, {"file": "gateway/src/middleware/rateLimit.ts", "line": 8, "severity": "minor", "issue": "`if (!key)` returns 401 for a missing key, but the acceptance criteria and plan do not specify this behavior, and the key is not validated against the existing auth layer; the plan asked to reuse the gateway's existing API-key extraction and validation.", "suggested_fix": "Delegate key extraction and validation to the existing auth middleware and run rate limiting after it, or confirm the 401 matches existing gateway behavior."}]}

## Stage output: release_note
{"title": "Per-API-key rate limiting now applied at the gateway", "summary": "Requests made with an API key are now limited to 100 per 60-second fixed window. Requests above this limit receive an error response until the window resets, so one integration can no longer slow requests from other clients.", "changes": ["Each API key is limited to 100 requests per 60-second fixed window.", "Requests beyond the limit within a window are rejected until the window resets."], "breaking": false, "upgrade_notes": "Integrations that send more than 100 requests per minute with a single API key must reduce their request rate or spread traffic across keys. Retry logic should handle rejected requests by waiting until the window resets."}