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
{
  "severity": "P1",
  "category": "feature",
  "component": "api",
  "summary": "Add repository method to find active users by email excluding soft-deleted rows to fix signup duplicate warnings.",
  "risk_flags": [
    "user-supplied input handling"
  ],
  "needs_security_review": true
}

## Stage output: requirements
{"user_story": "As a new user attempting to sign up, I want my registration to succeed even if I previously deleted an account with the same email, so that I am not blocked by soft-deleted records.", "acceptance_criteria": ["Given a signup request with an email address, When the system queries the user repository using find_active_by_email, Then it must return no results if the matching row exists but has a non-NULL deleted_at timestamp.", "Given a signup request with an email address, When the system queries the user repository using find_active_by_email, Then it must return the active user record if the matching row exists and has a NULL deleted_at timestamp.", "Given a signup request with an email address containing mixed-case characters, When the system queries the user repository using find_active_by_email, Then the search must be case-insensitive against stored emails that were lowercased on write or legacy mixed-case rows.", "Given a signup request with an email address that does not exist in the database, When the system queries the user repository using find_active_by_email, Then it must return None/NULL to indicate no active account found.", "Given a direct call to find_active_by_email with an empty string, When the system executes the query, Then it must handle the input safely without raising an exception or returning false positives."], "non_goals": ["The existing admin user search endpoint must be modified to exclude soft-deleted users in this ticket.", "This change must introduce any new database migrations beyond the application logic layer."], "open_questions": []}

## Stage output: plan
{"steps":[{"id":1,"description":"Create find_active_by_email method in user repository module with raw SQL query filtering deleted_at IS NULL and using LOWER() for case-insensitive matching","files":["api/src/repositories/user_repository.py"]},{"id":2,"description":"Implement input validation to handle empty strings and sanitize email parameter before executing database query","files":["api/src/repositories/user_repository.py"]},{"id":3,"description":"Update signup service duplicate check logic to invoke find_active_by_email instead of existing search method","files":["api/src/services/signup_service.py"]},{"id":4,"description":"Add unit tests for find_active_by_email covering active user match, soft-deleted exclusion, case-insensitivity, non-existent email, and empty string handling","files":["api/tests/unit/repositories/test_user_repository.py"]},{"id":5,"description":"Add integration test verifying signup flow succeeds when re-registering with a previously deleted account's email","files":["api/tests/integration/test_signup_flow.py"]},{"id":6,"description":"Update API documentation or changelog to reflect new repository method availability","files":["docs/api.md","CHANGELOG.md"]}], "risks":[{"risk":"SQL injection via user-supplied email input","mitigation":"Use parameterized queries with psycopg placeholders instead of string formatting for the email argument"},{"risk":"Performance degradation on large datasets due to case-insensitive search","mitigation":"Ensure emails are lowercased at write time in existing migrations or rely on database index if available; add index hint if query planner chooses sequential scan"}],"test_plan":["Given a signup request with an email address, When the system queries the user repository using find_active_by_email, Then it must return no results if the matching row exists but has a non-NULL deleted_at timestamp.","Given a signup request with an email address, When the system queries the user repository using find_active_by_email, Then it must return the active user record if the matching row exists and has a NULL deleted_at timestamp.","Given a signup request with an email address containing mixed-case characters, When the system queries the user repository using find_active_by_email, Then the search must be case-insensitive against stored emails that were lowercased on write or legacy mixed-case rows.","Given a signup request with an email address that does not exist in the database, When the system queries the user repository using find_active_by_email, Then it must return None/NULL to indicate no active account found.","Given a direct call to find_active_by_email with an empty string, When the system executes the query, Then it must handle the input safely without raising an exception or returning false positives."]

## Stage output: review
{"verdict":"request_changes","findings":[{"file":"api/repositories/users.py","line":13,"severity":"blocker","issue":"SQL injection vulnerability: the method constructs a query using f-string interpolation for user-supplied email input (f\"WHERE lower(email) = lower('{email}')\"). This allows attackers to inject arbitrary SQL via the signup form.","suggested_fix":"Use psycopg parameterized queries with placeholders. Change the query to: \"SELECT id, email, created_at FROM users WHERE lower(email) = lower(%s) AND deleted_at IS NULL\" and pass email as a tuple argument to cur.execute().","file":"api/routes/signup.py","line":25,"severity":"major","issue":"Missing input validation for empty string. The acceptance criteria explicitly require handling empty strings safely, but the code passes form.email directly without checking if it is empty before calling find_active_by_email.","suggested_fix":"Add a guard clause in signup route: if not form.email or form.email.strip() == \"\": return HTTPException(status_code=400, detail=\"email is required\"). Alternatively, handle empty string inside find_active_by_email by returning None early after validation.","summary":"Blocker SQL injection via f-string interpolation and missing empty input validation. Fix query to use psycopg placeholders and add empty email guard."}]

## Stage output: release_note
{"title": "Signup now excludes soft-deleted user accounts", "summary": "The signup duplicate check now uses a new repository method that returns only active users, excluding those with deleted_at timestamps set.", "changes": ["Signup requests no longer trigger duplicate warnings for emails belonging to soft-deleted accounts.", "The system performs case-insensitive matching against stored email addresses."], "breaking": false, "upgrade_notes": ""}