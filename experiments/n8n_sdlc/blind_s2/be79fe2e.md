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
{"severity": "P1", "category": "bug", "component": "notifications", "summary": "Webhook deliveries are dropped permanently on transient receiver failures, losing 312 invoice.paid events in one incident. Add retries with exponential backoff for timeouts, connection errors and 5xx, excluding 4xx.", "risk_flags": ["silent event loss for customers", "retry must exclude 4xx including 410 Gone to avoid endpoint auto-disable misbehavior", "possible duplicate delivery on retry if receiver partially processed", "max 5 attempts then mark failed"], "needs_security_review": false}

## Stage output: requirements
{"user_story": "As an integrations customer, I want transient webhook delivery failures to be retried with exponential backoff so that events such as invoice.paid are not permanently lost when my receiving server has a short outage", "acceptance_criteria": ["Given a delivery attempt fails with a network timeout, a connection error, or an HTTP 5xx response, when the attempt count is below 5, then the delivery is retried automatically.", "Given a delivery attempt receives an HTTP 4xx response (including 410 Gone), when the response is handled, then no retry is scheduled and the endpoint-disabling behaviour for 410 is unchanged.", "Given consecutive retryable failures, when retries are scheduled, then the wait before each retry is 2s, 4s, 8s and 16s respectively, for a maximum of 5 attempts in total.", "Given a retry is scheduled, when it is queued, then a WARNING log entry is written that includes the delivery id.", "Given all 5 attempts have failed with retryable errors, when the final attempt fails, then the delivery status is set to `failed` and no further attempts are made."], "non_goals": ["Changing the 4xx handling or the auto-disable behaviour for 410 Gone endpoints", "Deduplicating events or guaranteeing exactly-once delivery to receivers", "Replaying or recovering the 312 events lost in the past incident", "Adding a configurable retry policy or per-customer retry settings"], "open_questions": ["Should retries use the Celery retry mechanism or a delivery-table scheduler, and does the delivery worker need to survive a worker restart mid-backoff?", "Is the 2-second base delay and 2x multiplier fixed, or should jitter be applied to avoid synchronized retries after a customer outage?", "What request timeout value should count as a network timeout for classification?", "Given the triage risk of duplicate delivery when a receiver partially processed a request, should receivers be told to use the delivery id for idempotency, and is that documentation in scope?", "Should a successful retry be recorded on the delivery (e.g., attempt count), and is that field needed in the output?"]}

## Stage output: plan
{"steps": [{"id": 1, "description": "Read the existing delivery worker and HTTP send path in the notifications service to confirm where the single attempt happens, how 4xx and 410 Gone are currently classified, and where the delivery status is written.", "files": ["notifications/workers/webhook_delivery.py", "notifications/delivery/http_client.py"]}, {"id": 2, "description": "Add a small classification helper that returns retryable for network timeouts, connection errors and HTTP 5xx, and non-retryable for all other outcomes including 4xx and 410 Gone, leaving the existing 410 auto-disable call path untouched.", "files": ["notifications/delivery/http_client.py"]}, {"id": 3, "description": "Wire retries into the delivery task using the existing Celery task retry mechanism with countdown values of 2, 4, 8 and 16 seconds and max_retries set so that the total attempt count is 5, passing the attempt number through the task kwargs.", "files": ["notifications/workers/webhook_delivery.py"]}, {"id": 4, "description": "Emit a WARNING log entry with the delivery id each time a retry is scheduled, reusing the delivery id already present in the task kwargs.", "files": ["notifications/workers/webhook_delivery.py"]}, {"id": 5, "description": "On the final failed attempt (retryable error with no retries remaining, or any non-retryable error), set the delivery status to failed using the existing status update path and stop without further scheduling.", "files": ["notifications/workers/webhook_delivery.py", "notifications/models/delivery.py"]}, {"id": 6, "description": "Add unit tests for the classifier and for the task retry flow covering each acceptance criterion, using mocked HTTP responses and an eager or stubbed Celery configuration.", "files": ["notifications/tests/test_webhook_delivery.py", "notifications/tests/test_http_client.py"]}],
"risks": ["Retrying 410 Gone or other 4xx would trigger unintended endpoint auto-disable behaviour; mitigate by making the classifier explicitly allowlist retryable cases and asserting 4xx and 410 are non-retryable in tests.", "Duplicate delivery if the receiver partially processed a request before timing out; mitigate by including the delivery id in the request (already present) and flagging in release notes that receivers should use it for idempotency, since deduplication is out of scope.", "Celery retry state is lost or altered if the worker restarts mid-backoff; mitigate by relying on Celery's broker-persisted retry scheduling and confirming acknowledgement settings (acks_late) match the expected behaviour before merge.", "Retry storms against a recovering customer endpoint because backoff is not jittered; mitigate by keeping the fixed 2/4/8/16s schedule as specified and noting jitter as a follow-up decision.", "Changing the final status semantics could affect dashboards or alerts that count pending versus failed deliveries; mitigate by checking for existing consumers of the status field before changing the write path."],
"test_plan": ["Given a mocked response raising a network timeout, the classifier returns retryable and the task schedules a retry (AC1).", "Given a mocked connection error, the classifier returns retryable and the task schedules a retry (AC1).", "Given a mocked HTTP 503 and 500, the classifier returns retryable and the task schedules a retry while attempts remain below 5 (AC1).", "Given a mocked HTTP 400, 404 and 422, no retry is scheduled and the delivery is not left in a pending state (AC2).", "Given a mocked HTTP 410 Gone, no retry is scheduled and the existing endpoint auto-disable call is still invoked exactly once (AC2).", "Given consecutive retryable failures, the countdown values passed to retry are 2, 4, 8 and 16 seconds in order (AC3).", "Given the fifth consecutive retryable failure, no further retry is scheduled and the total attempt count is exactly 5 (AC3, AC5).", "Given a retry is scheduled, a WARNING log record is emitted containing the delivery id (AC4).", "Given all 5 attempts fail with retryable errors, the final delivery status is set to failed (AC5).", "Given a retry followed by a success, the delivery is marked successful and no further retries are scheduled (regression for the success path)."]}

## Stage output: review
{"verdict": "request_changes", "findings": [{"file": "notifications/delivery.py", "line": 17, "severity": "blocker", "issue": "The retry condition `if resp.status_code < 400: return \"delivered\"` followed by unconditional retry on any other non-success status means HTTP 4xx responses (including 410 Gone) are retried. The ticket and AC2 require no retry on 4xx, and 410 Gone must not be retried because it triggers endpoint auto-disable.", "suggested_fix": "Only retry when `resp.status_code >= 500`; for any other non-2xx status (4xx) return \"failed\" immediately, leaving the 410 handling path unchanged."}, {"file": "notifications/delivery.py", "line": 12, "severity": "major", "issue": "The `time.sleep(delay)` call runs after both the HTTP-status branch and the exception branch, but the 4xx path also falls through to it, and the sleep happens before the retry log on the final attempt is skipped correctly only by accident. Retry-scheduling is also synchronous: `time.sleep` blocks the Celery worker for up to 14s per delivery, contrary to the plan's use of Celery's retry mechanism with countdown.", "suggested_fix": "Use the Celery task retry (`self.retry(countdown=2**n)`) so waits are scheduled through the broker rather than blocking a worker slot, and make the 4xx path return immediately without sleeping."}, {"file": "notifications/delivery.py", "line": 24, "severity": "major", "issue": "`resp.status_code < 400` treats 1xx/3xx as delivered and everything else as retryable; the classifier is inverted relative to the agreed rule that only timeouts, connection errors and 5xx are retryable. Any future non-5xx error code falls into the retry loop.", "suggested_fix": "Explicitly allowlist retryable cases: `if 500 <= resp.status_code < 600` retry, `elif resp.ok` return delivered, else return failed."}, {"file": "notifications/delivery.py", "line": 14, "severity": "minor", "issue": "The delivery id is interpolated via `%s` and is correct, but the WARNING for 5xx retries is emitted before knowing whether another attempt will occur; the log text does not include the attempt number or delay, which makes the 2/4/8/16 schedule hard to verify in logs.", "suggested_fix": "Include `attempt` and `delay` in the warning message."}]], "summary": "Retry loop retries all non-2xx responses including 4xx and 410 Gone, violating the agreed rule. Retries also block the worker via time.sleep instead of Celery scheduling. Requires fixing the classifier and retry mechanism before merge."}

## Stage output: release_note
The review verdict is request_changes with a blocker, so the change is not yet merged. Per the instructions, I should write the note for the shipped behaviour the ticket describes, without treating unresolved review findings as shipped features. The ticket and acceptance criteria define the intended behaviour, so I'll describe that, and I'll flag the readiness concern in my reply outside the JSON since it is not part of the customer note. The output must be exactly one JSON object, so the caveat is in the text below the JSON.

{"title": "Webhook deliveries now retry transient failures", "summary": "Webhook deliveries that fail with a network timeout, a connection error, or an HTTP 5xx response are now retried automatically. Up to 5 attempts are made in total, with waits of 2, 4, 8 and 16 seconds between them. Deliveries that receive a 4xx response are not retried. A delivery that fails all attempts is marked failed.", "changes": ["Network timeouts, connection errors and HTTP 5xx responses to a webhook delivery are retried automatically.", "Each delivery makes at most 5 attempts, with waits of 2, 4, 8 and 16 seconds between attempts.", "HTTP 4xx responses, including 410 Gone, are not retried.", "A delivery that fails all 5 attempts is marked failed. Each scheduled retry is logged at WARNING with the delivery id."], "breaking": false, "upgrade_notes": "Receivers may now get the same event more than once if a request was processed but the response was lost or returned as a 5xx. Use the delivery id to make your handler idempotent."}

Note for the team: the review blocker (4xx responses currently retried, including 410 Gone, which would trigger endpoint auto-disable) and the blocking `time.sleep` must be fixed before this note is published as accurate. The note above describes the intended behaviour from the ticket and acceptance criteria, so it should be checked against the merged code once those findings are resolved.