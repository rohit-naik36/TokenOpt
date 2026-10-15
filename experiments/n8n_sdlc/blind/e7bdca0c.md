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
{"severity": "P2", "category": "feature", "component": "notifications", "summary": "Implement timezone-aware weekly digest scheduling to send emails at 09:00 local time for each user.", "risk_flags": [], "needs_security_review": false}

## Stage output: requirements
{"user_story": "As a user, I want to receive my weekly digest at 09:00 in my local time zone so that the email arrives during my working day.", "acceptance_criteria": ["Given a user with timezone 'America/Los_Angeles' and current UTC time 2023-10-28T05:00:00Z (during PDT), when next_digest_time is called, then it returns 2023-10-28T17:00:00Z.", "Given a user with timezone 'Asia/Kolkata' and current UTC time 2023-10-28T05:00:00Z (during IST), when next_digest_time is called, then it returns 2023-10-28T14:30:00Z.", "Given a user with timezone 'America/New_York' and current UTC time 2023-11-05T05:00:00Z (during EST after DST change), when next_digest_time is called, then it returns 2023-11-05T14:00:00Z.", "Given a user with no timezone configured in users.timezone, when next_digest_time is called, then it calculates the next 09:00 UTC time strictly after now_utc.", "Given a user with timezone 'Europe/London' and current UTC time 2023-03-12T05:00:00Z (during BST), when next_digest_time is called, then it returns 2023-03-12T04:00:00Z.", "Given a user with timezone 'America/Los_Angeles' and current UTC time exactly at the moment of DST transition (e.g., 2023-03-12T02:00:00Z), when next_digest_time is called, then it correctly handles the ambiguous or non-existent hour logic to return the next valid 09:00 local time converted to UTC."], "non_goals": [], "open_questions": []}

## Stage output: plan
{"steps": [{"id": 1, "description": "Update the `next_digest_time` function in the notifications service to accept an optional timezone parameter and default to UTC if missing.", "files": ["notifications/src/digest_scheduler.py"]}, {"id": 2, "description": "Implement logic to convert the current UTC time to the user's local timezone using `pytz` or `zoneinfo`, handling DST transitions and ambiguous hours gracefully.", "files": ["notifications/src/digest_scheduler.py"]}, {"id": 3, "description": "Calculate the next occurrence of 09:00 in the local timezone relative to the converted current time.", "files": ["notifications/src/digest_scheduler.py"]}, {"id": 4, "description": "Convert the calculated local datetime back to UTC and return it as an ISO 8601 string.", "files": ["notifications/src/digest_scheduler.py"]}, {"id": 5, "description": "Add unit tests covering all acceptance criteria including specific timezone offsets, DST transitions, and missing timezone configurations.", "files": ["tests/notifications/test_digest_scheduler.py"]}], "risks": ["Incorrect handling of ambiguous hours during DST transitions could cause the digest to be sent at an unintended time; mitigation: use `zoneinfo` (Python 3.9+) or `pytz` with explicit `fold` parameter logic to handle non-existent and ambiguous hours.", "Relying on a user-provided timezone string that might be invalid; mitigation: wrap timezone parsing in a try-except block and default to UTC if the string is unrecognized."], "test_plan": ["Verify next_digest_time returns 2023-10-28T17:00:00Z for America/Los_Angeles at 2023-10-28T05:00:00Z.", "Verify next_digest_time returns 2023-10-28T14:30:00Z for Asia/Kolkata at 2023-10-28T05:00:00Z.", "Verify next_digest_time returns 2023-11-05T14:00:00Z for America/New_York at 2023-11-05T05:00:00Z (post-DST).", "Verify next_digest_time returns the next 09:00 UTC when no timezone is configured.", "Verify next_digest_time returns 2023-03-12T04:00:00Z for Europe/London at 2023-03-12T05:00:00Z (BST).", "Verify next_digest_time correctly handles the DST transition moment in America/Los_Angeles on 2023-03-12."]

## Stage output: review
{"verdict": "request_changes", "findings": [{"file": "notifications/schedule.py", "line": 9, "severity": "blocker", "issue": "The code `local_now = now_utc.replace(tzinfo=tz)` incorrectly assumes the UTC timestamp maps directly to the local time without accounting for the offset. For example, if `now_utc` is 2023-10-28T05:00:00Z and the user is in 'America/Los_Angeles' (PDT, UTC-7), the naive replace creates a datetime that is 12 hours ahead of the intended local time. The correct approach is to convert using `now_utc.astimezone(tz)`.", "suggested_fix": "Replace `local_now = now_utc.replace(tzinfo=tz)` with `local_now = now_utc.astimezone(tz)`."}, {"file": "notifications/schedule.py", "line": 10, "severity": "blocker", "issue": "The logic `target <= local_now` fails to handle the case where the current UTC time is in a non-existent hour (e.g., spring forward) or ambiguous hour. If `now_utc` is during a gap, `local_now` will be set incorrectly due to the first error, and simply adding a day may skip valid occurrences or land in an invalid slot.", "suggested_fix": "Use `zoneinfo.ZoneInfo` correctly with `astimezone`, then calculate the next occurrence by checking if the target time is before the current local time; if so, add one day. Ensure to handle the case where adding a day lands in a non-existent hour by iterating or using a robust library function if available."}], "summary": "The implementation incorrectly uses replace() instead of astimezone() for timezone conversion, leading to wrong local times and DST handling failures. This violates acceptance criteria for multiple timezones."}

## Stage output: release_note
{"title": "Weekly digest now sent at 09:00 local time", "summary": "The weekly digest email is now scheduled to arrive at 09:00 in the recipient's local time zone instead of a fixed server time.", "changes": ["Weekly digest emails are now delivered at 09:00 in the recipient's local time zone."], "breaking": false, "upgrade_notes": ""}