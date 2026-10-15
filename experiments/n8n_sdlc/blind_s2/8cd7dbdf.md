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
{"severity": "P2", "category": "bug", "component": "api", "summary": "Soft-deleted users appear in admin search and trigger false duplicate-account warnings on signup. Add a case-insensitive active-only lookup by email to the user repository and use it in the signup duplicate check.", "risk_flags": ["unauthenticated signup input reaches raw SQL", "case-insensitive matching on legacy mixed-case rows", "blocks re-registration of deleted accounts", "admin search also returns soft-deleted users"], "needs_security_review": true}

## Stage output: requirements
{"user_story": "As a signup user, I want the duplicate-email check to ignore soft-deleted accounts and match emails case-insensitively so that I can re-register with an email previously used by a deleted account and am not wrongly blocked by a false duplicate warning.", "acceptance_criteria": ["Given an active user with email 'Alice@Example.com' (stored in mixed case) and no soft-deleted rows, when `find_active_by_email('alice@example.com')` is called, then the repository returns that user.", "Given a user whose `deleted_at` is set and whose email is 'bob@example.com', when `find_active_by_email('bob@example.com')` is called, then the repository returns None.", "Given no user with a matching email (ignoring case) exists, when `find_active_by_email` is called, then the repository returns None.", "Given a signup request whose email matches only a soft-deleted user, when the signup duplicate check runs, then no duplicate-account warning is raised and the signup proceeds.", "Given a signup request whose email matches an active user case-insensitively, when the signup duplicate check runs, then the duplicate-account warning is raised.", "Given an email value supplied from the unauthenticated signup form, when it is passed to `find_active_by_email`, then it is bound as a query parameter and not interpolated into the SQL string."], "non_goals": ["Changing admin user search behaviour to exclude soft-deleted users (reported in the triage risk flags but not requested in this ticket's description; to be tracked separately unless confirmed in scope).", "Backfilling or normalising legacy mixed-case email rows in the database.", "Changing how emails are lowercased on write.", "Any ORM introduction; the module continues to use raw SQL with psycopg 3."], "open_questions": ["Should the admin user search fix mentioned in the description and triage summary be included in this ticket or split into a separate ticket?", "Is a database index on lower(email) required for performance, and is the expected table size known?", "If multiple active users match the same email case-insensitively (possible with legacy data), should the method return the first match, the oldest, or raise an error?", "Does the signup flow need to surface a different message for a soft-deleted match, or should it proceed silently?", "Has the security review requested by the triage stage been scheduled, and are there rate-limit or enumeration-protection requirements for the signup duplicate check?"]}

## Stage output: plan
{"steps": [{"id": 1, "description": "Add a `find_active_by_email(email)` method to the user repository that runs a parameterized psycopg 3 query matching `lower(email) = lower(%s)` with `deleted_at IS NULL`, returning the user row or None.", "files": ["api/repositories/user_repository.py"]}, {"id": 2, "description": "Define the return type of `find_active_by_email` consistently with the other repository lookups in the module, reusing the existing user row-to-model mapping rather than introducing a new mapper.", "files": ["api/repositories/user_repository.py", "api/models/user.py"]}, {"id": 3, "description": "Replace the existing email duplicate check in the signup flow so it calls `find_active_by_email` and raises the duplicate-account warning only when an active match is returned, leaving the rest of the signup flow unchanged.", "files": ["api/services/signup.py"]}, {"id": 4, "description": "Add repository-level tests covering case-insensitive matching, exclusion of soft-deleted rows, the no-match case, and confirmation that the email is passed as a bound parameter.", "files": ["api/tests/repositories/test_user_repository.py"]}, {"id": 5, "description": "Add signup service tests covering the soft-deleted-only match (signup proceeds) and the active case-insensitive match (warning raised), mocking the repository as needed.", "files": ["api/tests/services/test_signup.py"]}], "risks": ["Unauthenticated signup input reaches SQL; mitigate by strictly using psycopg 3 parameter binding and never formatting the email into the query string, and flag for the requested security review.", "`lower(email)` cannot use a plain index on `email`, so the query may table-scan at scale; mitigate by checking table size and adding an expression index on `lower(email)` in a separate migration if needed (open question).", "Legacy mixed-case data may yield multiple active matches; mitigate by defining deterministic behaviour (e.g. LIMIT 1 with ORDER BY created_at) and confirming with the product owner.", "Admin user search continues to return soft-deleted users; mitigate by keeping it out of scope per the non-goals and tracking it as a separate ticket so this PR does not widen its blast radius.", "Enumeration risk from the signup duplicate check reveals whether an email is registered; mitigate by deferring to the security review for rate limiting or response-shape changes, without altering the response in this PR."], "test_plan": ["Repository: an active user stored as 'Alice@Example.com' is returned when queried with 'alice@example.com' (covers AC1).", "Repository: a user with `deleted_at` set and a matching email returns None (covers AC2).", "Repository: querying an email with no matching row, in any case, returns None (covers AC3).", "Signup service: a signup whose email matches only a soft-deleted user raises no duplicate warning and proceeds (covers AC4).", "Signup service: a signup whose email matches an active user case-insensitively raises the duplicate warning (covers AC5).", "Repository: inspect the executed SQL or use a malicious-looking email (e.g. containing quotes and `OR 1=1`) to confirm it is bound as a parameter and does not alter the result set (covers AC6).", "Regression: existing signup tests for unique, non-matching emails still pass unchanged."]}

## Stage output: review
{"verdict": "request_changes", "findings": [{"file": "api/repositories/users.py", "line": 16, "severity": "blocker", "issue": "The email is interpolated into the SQL via f-string: `lower('{email}')`. The signup form is unauthenticated, so any visitor can inject SQL (e.g. a quote followed by `OR 1=1 --`), exposing or altering user data. This directly violates acceptance criterion 6 requiring the email to be bound as a query parameter.", "suggested_fix": "Use a parameterized query: cur.execute(\"SELECT id, email, created_at FROM users WHERE lower(email) = lower(%s) AND deleted_at IS NULL\", (email,))"}, {"file": "api/repositories/users.py", "line": 19, "severity": "major", "issue": "The method uses fetchone() without an ORDER BY or LIMIT, so when legacy mixed-case data yields multiple active matches the returned row is nondeterministic. The plan calls for deterministic behaviour (e.g. ORDER BY created_at).", "suggested_fix": "Add ORDER BY created_at LIMIT 1 to the query so the returned match is deterministic, and confirm the chosen ordering with the product owner."}, {"file": "api/repositories/users.py", "line": 22, "severity": "minor", "issue": "The method returns a raw tuple, while the plan (step 2) requires reusing the module's existing row-to-model mapping used by other lookups; callers may rely on attribute access the other lookups provide.", "suggested_fix": "Map the row through the same helper used by find_by_email so the return type is consistent, or return None explicitly when no row matches."}]
, "summary": "SQL injection via f-string on unauthenticated signup email is a blocker; also needs deterministic ordering and consistent return mapping before merge."}

## Stage output: release_note
{"title": "Email lookup now ignores deleted accounts and matches case-insensitively", "summary": "The signup duplicate-email check now ignores soft-deleted accounts, so people can re-register with an email used by a deleted account. Email matching is now case-insensitive. Duplicate-account warnings are raised only for active accounts.", "changes": ["The signup duplicate-email check no longer matches soft-deleted accounts, so re-registration with a previously deleted account's email is allowed.", "The signup duplicate-email check matches emails case-insensitively, so 'Alice@Example.com' and 'alice@example.com' are treated as the same address."], "breaking": false, "upgrade_notes": ""}