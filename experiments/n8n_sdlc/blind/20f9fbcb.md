## Ticket
{
  "id": "T02",
  "title": "Webhook delivery: retry transient failures with backoff",
  "type": "bug",
  "priority_hint": "Medium",
  "reporter": "integrations-pm",
  "labels": [
    "notifications",
    "webhooks",
    "reliability"
  ],
  "description": "Customer webhooks are delivered once and dropped if the receiving server hiccups. Last week a customer's deploy caused 4 minutes of 503s and we lost 312 `invoice.paid` events. Add retries to the delivery worker.\n\nRules agreed with the integrations team: retry on network timeouts, connection errors and HTTP 5xx only. Never retry on 4xx (the customer has told us the payload is wrong or the endpoint is gone). Maximum 5 attempts in total, with exponential backoff starting at 2 seconds (2s, 4s, 8s, 16s). Log each retry at WARNING with the delivery id. After the last failure mark the delivery `failed`.",
  "environment": "Python 3.12, `requests`, Celery worker. Service: notifications.",
  "comments": [
    "integrations-pm: Please do not retry 410 Gone, we auto-disable the endpoint on that.",
    "backend-dev: Delivery id is already in the task kwargs, I will log it."
  ]
}

## Diff
diff --git a/notifications/delivery.py b/notifications/delivery.py
--- a/notifications/delivery.py
+++ b/notifications/delivery.py
@@ -1,25 +1,42 @@
 import logging
+import time

 import requests

 log = logging.getLogger(__name__)

+MAX_ATTEMPTS = 5
+BASE_DELAY = 2
+

 def deliver(delivery_id: str, url: str, payload: dict) -> str:
-    try:
-        resp = requests.post(url, json=payload, timeout=10)
-    except requests.RequestException:
-        return "failed"
-    return "delivered" if resp.ok else "failed"
+    delay = BASE_DELAY
+    for attempt in range(1, MAX_ATTEMPTS + 1):
+        try:
+            resp = requests.post(url, json=payload, timeout=10)
+            if resp.status_code < 400:
+                return "delivered"
+            if attempt == MAX_ATTEMPTS:
+                return "failed"
+            log.warning("retrying delivery %s after HTTP %s", delivery_id, resp.status_code)
+        except (requests.Timeout, requests.ConnectionError):
+            if attempt == MAX_ATTEMPTS:
+                return "failed"
+            log.warning("retrying delivery %s after network error", delivery_id)
+        time.sleep(delay)
+        delay *= 2
+    return "failed"


## Stage output: triage
{"severity": "P1", "category": "feature", "component": "notifications", "summary": "Add retry logic with exponential backoff for transient webhook delivery failures to prevent data loss.", "risk_flags": ["data loss"], "needs_security_review": false}

## Stage output: requirements
{"user_story": "As a customer integration engineer, I want webhook deliveries to retry transient failures with exponential backoff so that I do not lose events during brief service outages.", "acceptance_criteria": ["Given a webhook delivery fails with a network timeout or connection error, When the worker retries, Then it must wait 2 seconds before the first attempt and double the wait time for each subsequent attempt up to a maximum of 5 total attempts.", "Given a webhook delivery receives an HTTP 5xx status code, When the worker retries, Then it must apply exponential backoff starting at 2 seconds and log each retry as WARNING with the delivery id.", "Given a webhook delivery receives an HTTP 4xx status code, When the worker attempts to deliver, Then it must not retry and mark the delivery as failed immediately.", "Given a webhook delivery has exhausted all 5 retry attempts after transient failures, When the final attempt fails, Then the delivery status must be marked as 'failed'.", "Given a webhook delivery succeeds on any attempt within the 5-attempt limit, When the request returns a 2xx status code, Then the delivery must be marked as 'delivered' and no further retries must occur.", "Given a webhook delivery is retried, Then the wait times between attempts must strictly follow the sequence of 2s, 4s, 8s, 16s based on the attempt number."], "non_goals": [], "open_questions": []}

## Stage output: plan
{"steps":[{"id":1,"description":"Add retry configuration constants and helper function for exponential backoff calculation in notifications module","files":["notifications/config.py"]},{"id":2,"description":"Update webhook delivery worker to catch network errors, apply backoff delays, and log retries as WARNING","files":["notifications/worker.py"]},{"id":3,"description":"Modify HTTP response handler to distinguish 5xx (retry) from 4xx (fail immediately) status codes","files":["notifications/handler.py"]},{"id":4,"description":"Implement state machine logic to track attempt count, enforce max 5 attempts, and update delivery status on final failure or success","files":["notifications/state.py"]},{"id":5,"description":"Add unit tests for transient failure retry sequences with correct timing intervals","files":["tests/test_webhook_retry.py"]},{"id":6,"description":"Add integration tests verifying HTTP 4xx immediate failure and HTTP 5xx exponential backoff behavior","files":["tests/integration/test_delivery_flows.py"]},{"id":7,"description":"Verify delivery status transitions to 'failed' after exhausting retries or 'delivered' on success in test suite","files":["tests/test_webhook_retry.py"]}], "risks": ["Data loss: Mitigate by ensuring no messages are dropped during retry logic; only mark as failed after max attempts or immediate 4xx rejection.", "Performance impact: Mitigate by limiting max retries to 5 and capping backoff at 16s to prevent long tail latency."], "test_plan": ["Verify first retry wait is 2 seconds and subsequent waits are 4s, 8s, 16s for transient failures.","Confirm HTTP 5xx responses trigger retries with WARNING logs and correct delays.","Ensure HTTP 4xx responses fail immediately without retries.","Validate delivery status changes to 'failed' after 5th attempt failure.","Validate delivery status changes to 'delivered' on any 2xx response within attempts."]}

## Stage output: review
{"verdict":"request_changes","findings":[{"file":"notifications/delivery.py","line":18,"severity":"blocker","issue":"The loop iterates with `for attempt in range(1, MAX_ATTEMPTS + 1)` which executes exactly 5 times (attempts 1-5), but the backoff delay is applied after every iteration including the final one. The acceptance criteria require waiting before retries; on the 5th attempt there should be no wait and no retry logic since it is the last attempt.","suggested_fix":"Change the loop to `for attempt in range(MAX_ATTEMPTS):` and adjust indexing so that attempt 0 corresponds to the first try, then calculate delay based on `attempt` (0-based) before sleeping, ensuring no sleep occurs on the final (5th) attempt."},{"file":"notifications/delivery.py","line":27,"severity":"major","issue":"The code logs a warning for network errors but does not distinguish between transient failures that warrant retrying versus permanent failures. The acceptance criteria specify retrying only on timeouts/connection errors, yet the current exception handler catches all `requests.RequestException` which may include non-retryable errors like DNS failures or SSL certificate errors.","suggested_fix":"Refine the exception handling to specifically catch `(requests.Timeout, requests.ConnectionError)` as shown in the diff for HTTP errors, but ensure network exceptions are also limited to transient types only, logging a different severity or skipping retry for non-transient RequestExceptions."},{"file":"notifications/delivery.py","line":21,"severity":"minor","issue":"The code returns 'failed' immediately on any 4xx status code without attempting retries, which aligns with the acceptance criteria. However, it does not explicitly log the failure reason or mark the delivery as failed in a way that matches the state machine logic described in the plan.","suggested_fix":"Add logging for 4xx failures to ensure observability: `log.error('delivery %s failed immediately after HTTP %s', delivery_id, resp.status_code)` before returning 'failed'."}],"summary":"Loop runs one extra iteration causing unnecessary sleep on final attempt; exception handling too broad for network errors; missing log for 4xx immediate failure."}

## Stage output: release_note
{"title": "Webhooks now retry transient failures with backoff", "summary": "The system now automatically retries webhook deliveries that fail due to transient errors using exponential backoff. This prevents event loss during brief service outages.", "changes": ["Webhook delivery failures caused by transient errors are now retried with exponential backoff."], "breaking": false, "upgrade_notes": ""}