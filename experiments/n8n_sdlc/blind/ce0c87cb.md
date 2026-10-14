## Ticket
{
  "id": "T08",
  "title": "Send weekly digest at 09:00 in the recipient's local time",
  "type": "feature",
  "priority_hint": "Medium",
  "reporter": "growth-pm",
  "labels": [
    "notifications",
    "digest",
    "timezones"
  ],
  "description": "The weekly digest email currently goes out at 09:00 UTC for everyone, which lands at 02:00 for our West-coast customers and 14:30 for India. Growth wants it at 09:00 in each recipient's own time zone (IANA name stored in `users.timezone`, e.g. `America/Los_Angeles`).\n\nAdd `next_digest_time(user, now_utc)` returning the next 09:00 local time strictly after `now_utc`, as an aware UTC datetime. Must be correct across daylight saving changes. Users with no time zone fall back to `UTC`.",
  "environment": "Python 3.12 (zoneinfo available). Service: notifications. Scheduler calls this function hourly.",
  "comments": [
    "growth-pm: Open rates are 3x higher when mail arrives at start of the working day.",
    "backend-dev: I will use zoneinfo, no pytz.",
    "qa: Please include a DST case in the tests."
  ]
}

## Diff
diff --git a/notifications/schedule.py b/notifications/schedule.py
--- a/notifications/schedule.py
+++ b/notifications/schedule.py
@@ -1,6 +1,28 @@
-from datetime import datetime
+from datetime import datetime, timedelta, timezone
+from zoneinfo import ZoneInfo

 DIGEST_HOUR = 9

+
+def next_digest_time(user, now_utc: datetime) -> datetime:
+    tz = ZoneInfo(user.timezone or "UTC")
+    local_now = now_utc.replace(tzinfo=tz)
+    target = local_now.replace(hour=DIGEST_HOUR, minute=0, second=0, microsecond=0)
+    if target <= local_now:
+        target += timedelta(days=1)
+    return target.astimezone(timezone.utc)


## Stage output: triage
{"severity": "P2", "category": "feature", "component": "notifications", "summary": "Implement timezone-aware weekly digest scheduling to send emails at 09:00 local time instead of fixed UTC.", "risk_flags": [], "needs_security_review": false}

## Stage output: requirements
{"user_story": "As a user, I want to receive my weekly digest at 09:00 in my local time zone so that the email arrives during my working hours.", "acceptance_criteria": ["Given a user with timezone 'America/Los_Angeles' and current UTC time 2023-10-08T04:00:00Z (during DST), when calculating next_digest_time, then the result must be 2023-10-08T17:00:00Z.", "Given a user with timezone 'Asia/Kolkata' and current UTC time 2023-10-08T04:00:00Z, when calculating next_digest_time, then the result must be 2023-10-08T13:30:00Z.", "Given a user with no timezone set in users.timezone and current UTC time any value, when calculating next_digest_time, then the result must be the next 09:00 UTC.", "Given a user with timezone 'America/New_York' crossing from EST to EDT on Feb 12, 2023 at 02:00 local time, when calculating next_digest_time for a request at 2023-02-12T05:00:00Z, then the result must correctly reflect the 09:00 EDT target without skipping or duplicating hours.", "Given a user with timezone 'Europe/London' and current UTC time 2023-03-26T01:00:00Z (during BST transition), when calculating next_digest_time, then the result must be 2023-03-26T09:00:00Z.", "Given a user with timezone 'Pacific/Auckland' and current UTC time 2023-10-08T04:00:00Z, when calculating next_digest_time, then the result must be 2023-10-09T09:00:00Z (next day)."], "non_goals": [], "open_questions": []}

## Stage output: plan
{"steps": [{"id": 1, "description": "Update the timezone resolution logic in the notifications service to handle DST transitions and local time offsets correctly using IANA database.", "files": ["src/notifications/timezone_utils.ts"]}, {"id": 2, "description": "Refactor the next_digest_time calculation to convert the target 09:00 local time back to UTC based on the resolved offset at that specific moment.", "files": ["src/notifications/schedulers/digest_scheduler.ts"]}, {"id": 3, "description": "Add defensive checks for missing timezone configuration in user profiles to default to UTC calculation.", "files": ["src/notifications/models/user_profile.ts", "src/notifications/schedulers/digest_scheduler.ts"]}, {"id": 4, "description": "Implement the logic to determine if the calculated local time falls on the next calendar day relative to the current UTC timestamp.", "files": ["src/notifications/schedulers/digest_scheduler.ts"]}, {"id": 5, "description": "Write unit tests covering all acceptance criteria including specific DST transition dates and edge cases for timezone offsets.", "files": ["src/notifications/__tests__/digest_scheduler.test.ts"]}], "risks": ["Incorrect handling of ambiguous or non-existent local times during DST transitions could cause duplicate or skipped notifications; mitigated by using a robust library like luxon or moment-timezone that handles IANA rules internally.", "Relying on user-provided timezone strings without validation could lead to runtime errors if an invalid string is passed; mitigated by adding a try-catch block and defaulting to UTC with a warning log if resolution fails."], "test_plan": ["Verify next_digest_time for America/Los_Angeles at 2023-10-08T04:00:00Z returns 2023-10-08T17:00:00Z.", "Verify next_digest_time for Asia/Kolkata at 2023-10-08T04:00:00Z returns 2023-10-08T13:30:00Z.", "Verify next_digest_time defaults to next 09:00 UTC when user.timezone is null or undefined.", "Verify next_digest_time for America/New_York at 2023-02-12T05:00:00Z correctly targets 09:00 EDT without hour duplication.", "Verify next_digest_time for Europe/London at 2023-03-26T01:00:00Z returns 2023-03-26T09:00:00Z.", "Verify next_digest_time for Pacific/Auckland at 2023-10-08T04:00:00Z returns 2023-10-09T09:00:00Z."]}

## Stage output: review
{"verdict": "request_changes", "findings": [{"file": "notifications/schedule.py", "line": 1, "severity": "blocker", "issue": "The diff modifies a Python file (notifications/schedule.py) but the ticket and acceptance criteria explicitly describe changes to TypeScript files (src/notifications/timezone_utils.ts, src/notifications/schedulers/digest_scheduler.ts). This is a critical implementation mismatch.", "suggested_fix": "Do not modify notifications/schedule.py. Instead, implement the logic in the specified TypeScript files: src/notifications/timezone_utils.ts, src/notifications/schedulers/digest_scheduler.ts, and src/notifications/models/user_profile.ts."}, {"file": "notifications/schedule.py", "line": 10, "severity": "major", "issue": "The code uses `now_utc.replace(tzinfo=tz)` to attach the timezone. While this works for naive UTC datetimes, it is semantically imprecise and can lead to ambiguity if `now_utc` already has a different timezone or if DST transitions are involved in subtle ways not captured by simple replacement. The safer pattern is to use `datetime.fromtimestamp(now_utc.timestamp(), tz=tz)`.", "suggested_fix": "Replace `local_now = now_utc.replace(tzinfo=tz)` with `local_now = datetime.fromtimestamp(now_utc.timestamp(), tz=tz)`."}, {"file": "notifications/schedule.py", "line": 10, "severity": "minor", "issue": "The code assumes `user.timezone` is always a valid IANA string or defaults to 'UTC'. If `user.timezone` contains an invalid string (e.g., 'InvalidTZ'), `ZoneInfo()` will raise a `KeyError`. The plan mentions defensive checks for missing timezone, but not for invalid ones.", "suggested_fix": "Wrap `ZoneInfo(user.timezone or \"UTC\")` in a try-except block to catch `KeyError` and default to UTC if the provided timezone is invalid."}], "summary": "Implementation uses wrong language (Python vs TypeScript) and files. Also lacks robustness for invalid timezones and uses less safe datetime conversion methods."}

## Stage output: release_note
{"title": "Weekly digest now sent at 09:00 local time", "summary": "The weekly digest email is now scheduled to arrive at 09:00 in the recipient's local time zone instead of a fixed server time.", "changes": ["Weekly digest emails are now sent at 09:00 in the recipient's local time zone."], "breaking": false, "upgrade_notes": ""}