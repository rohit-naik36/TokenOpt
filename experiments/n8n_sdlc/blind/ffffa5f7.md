## Ticket
{
  "id": "T06",
  "title": "Look up active users by email (exclude soft-deleted)",
  "type": "feature",
  "priority_hint": "Medium",
  "reporter": "backend-dev",
  "labels": [
    "api",
    "users",
    "signup"
  ],
  "description": "Soft-deleted users (those with `deleted_at` set) are still being returned by the admin user search and are triggering duplicate-account warnings on signup. Add `find_active_by_email(email)` to the user repository that returns the user whose email matches (case-insensitive) and whose `deleted_at` is NULL, or None. Use it from the signup duplicate check.",
  "environment": "Python 3.12, psycopg 3 (raw SQL, no ORM in this module), PostgreSQL 15. Service: api. The email comes from an unauthenticated signup form.",
  "comments": [
    "backend-dev: Emails are stored lowercased on write already, but legacy rows may be mixed case.",
    "pm: Signup duplicate check must not match deleted accounts, otherwise people cannot re-register."
  ]
}

## Diff
diff --git a/api/repositories/users.py b/api/repositories/users.py
--- a/api/repositories/users.py
+++ b/api/repositories/users.py
@@ -10,6 +10,18 @@ class UserRepository:
     def __init__(self, conn):
         self.conn = conn

+    def find_active_by_email(self, email: str):
+        query = (
+            "SELECT id, email, created_at FROM users "
+            f"WHERE lower(email) = lower('{email}') AND deleted_at IS NULL"
+        )
+        with self.conn.cursor() as cur:
+            cur.execute(query)
+            row = cur.fetchone()
+        return row
+
diff --git a/api/routes/signup.py b/api/routes/signup.py
--- a/api/routes/signup.py
+++ b/api/routes/signup.py
@@ -22,7 +22,7 @@ def signup(form: SignupForm, repo: UserRepository = Depends(get_repo)):
-    if repo.find_by_email(form.email):
+    if repo.find_active_by_email(form.email):
         raise HTTPException(status_code=409, detail="email already registered")


## Stage output: triage
{"severity": "P1", "category": "bug", "component": "api", "summary": "Fix user search to exclude soft-deleted accounts and prevent duplicate signup warnings.", "risk_flags": ["user-supplied input handling"], "needs_security_review": true}

## Stage output: requirements
{"user_story": "As a developer, I want to exclude soft-deleted users from email lookups so that duplicate account warnings are only triggered for truly active accounts.", "acceptance_criteria": ["Given the find_active_by_email method is called with an email address, When the repository queries users whose deleted_at is NULL and email matches case-insensitively, Then it returns the matching user or None if no match exists.", "Given the signup duplicate check uses find_active_by_email, When a soft-deleted user exists in the database, Then the method must not return that user and must not trigger a duplicate warning.", "Given the find_active_by_email method is called with an email address, When multiple active users share the same email (if allowed), Then it returns exactly one of them or None if none are active.", "Given the signup flow calls find_active_by_email, When the result is None, Then the system must proceed without raising a duplicate account error.", "Given the find_active_by_email method is called with an empty string, When no user has that email, Then it returns None."], "non_goals": [], "open_questions": []}

## Stage output: plan
{"steps":[{"id":1,"description":"Ensure find_active_by_email filters users where deleted_at is NULL and performs case-insensitive email matching","files":["src/api/repositories/user_repository.py"]},{"id":2,"description":"Handle empty string input by returning None without raising exceptions","files":["src/api/repositories/user_repository.py"]},{"id":3,"description":"Update signup service to consume find_active_by_email result and skip duplicate warning for soft-deleted users","files":["src/api/services/signup_service.py"]},{"id":4,"description":"Add unit test for active user lookup returning single match or None","files":["tests/api/test_user_repository.py"]},{"id":5,"description":"Add unit test verifying soft-deleted users are excluded from results","files":["tests/api/test_user_repository.py"]},{"id":6,"description":"Add unit test for empty string input returning None","files":["tests/api/test_user_repository.py"]},{"id":7,"description":"Add integration test confirming signup flow proceeds without error when find_active_by_email returns None","files":["tests/api/integration/test_signup_flow.py"]}],"risks":["user-supplied input handling: mitigate by validating email format and ensuring empty strings are handled gracefully before database query"],"test_plan":["Test find_active_by_email with valid active user email returns user object","Test find_active_by_email with soft-deleted user email returns None","Test find_active_by_email with non-existent email returns None","Test find_active_by_email with empty string returns None","Test signup duplicate check does not warn when only soft-deleted user exists","Test signup flow proceeds without error when find_active_by_email returns None"]}

## Stage output: review
{"verdict": "request_changes", "findings": [{"file": "api/repositories/users.py", "line": 13, "severity": "blocker", "issue": "SQL query uses string interpolation for email: f\"...lower('{email}')...\" which is vulnerable to SQL injection if email contains quotes or special characters.", "suggested_fix": "Use parameterized query: cur.execute(\"SELECT id, email, created_at FROM users WHERE lower(email) = lower(?) AND deleted_at IS NULL\", (email,))"}, {"file": "api/routes/signup.py", "line": 25, "severity": "major", "issue": "The route calls repo.find_active_by_email(form.email) but the method signature in the diff shows email: str without handling empty strings explicitly before DB access; if form.email is empty string, it passes to DB query which may fail or return unexpected results depending on DB behavior with NULL/empty comparisons.", "suggested_fix": "Add guard: if not form.email: return (or handle gracefully) before calling find_active_by_email"}], "summary": "SQL injection vulnerability via string interpolation and missing empty input validation."}

## Stage output: release_note
{"title": "Exclude soft-deleted users from email lookups", "summary": "The user lookup endpoint now excludes soft-deleted accounts. Duplicate warnings now only trigger for active accounts.", "changes": ["Soft-deleted users are excluded from results returned by the user lookup endpoint."], "breaking": false, "upgrade_notes": ""}