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
{"severity": "P2", "category": "bug", "component": "api", "summary": "Fix user search to exclude soft-deleted accounts and prevent duplicate account warnings during signup.", "risk_flags": ["user-supplied input handling"], "needs_security_review": true}

## Stage output: requirements
{"user_story": "As a developer, I want to filter out soft-deleted users when searching by email so that new signups do not trigger false duplicate-account warnings.", "acceptance_criteria": ["Given the user repository method find_active_by_email(email) is called with a valid email address, then it returns exactly one user if an active account exists and null otherwise.", "When find_active_by_email(email) is called with an email that matches only soft-deleted users (deleted_at is not NULL), then it returns null.", "Given find_active_by_email(email) is called with an email that matches both an active user and a soft-deleted user, then it returns the active user record where deleted_at is NULL.", "When find_active_by_email(email) is called with a case-insensitive match to multiple active users (if duplicates exist in DB), then it returns one of those active users without filtering by other criteria.", "Given find_active_by_email(email) is called with an email that does not exist in the database at all, then it returns null.", "When find_active_by_email(email) is integrated into the signup duplicate check flow, then the system must not flag a soft-deleted user as a duplicate for a new registration."], "non_goals": [], "open_questions": []}

## Stage output: plan
{"steps": [{"id": 1, "description": "Create find_active_by_email method in the user repository module that queries for users with a matching email and deleted_at is NULL", "files": ["src/api/repositories/user_repository.py"]}, {"id": 2, "description": "Implement case-insensitive email comparison logic within the query or pre-processing step to handle duplicate active accounts", "files": ["src/api/repositories/user_repository.py"]}, {"id": 3, "description": "Ensure the method returns null if no active user is found, regardless of soft-deleted matches", "files": ["src/api/repositories/user_repository.py"]}, {"id": 4, "description": "Update the signup service to call find_active_by_email instead of existing generic email lookup for duplicate checks", "files": ["src/api/services/signup_service.py"]}, {"id": 5, "description": "Add unit tests covering active user match, soft-deleted only match, mixed active/soft-deleted match, non-existent email, and case-insensitivity", "files": ["tests/api/repositories/test_user_repository.py"]}], "risks": ["SQL injection or unsafe string concatenation if email is not properly parameterized in the repository query (mitigation: use ORM parameter binding or raw SQL placeholders)", "Performance degradation if the query scans large tables without an index on email and deleted_at (mitigation: ensure composite index exists on users(email, deleted_at))"], "test_plan": ["Test find_active_by_email with a valid active user email expecting the user record", "Test find_active_by_email with an email matching only soft-deleted users expecting null", "Test find_active_by_email with an email matching both active and soft-deleted users expecting the active record", "Test find_active_by_email with multiple active users having the same email expecting one active record", "Test find_active_by_email with a non-existent email expecting null", "Verify signup flow does not flag soft-deleted accounts as duplicates when registering a new user"]

## Stage output: review
{"verdict": "request_changes", "findings": [{"file": "api/repositories/users.py", "line": 16, "severity": "blocker", "issue": "SQL injection vulnerability: the email parameter is directly interpolated into the SQL query string without parameterization (f\"...'{email}'..."), allowing attackers to inject malicious payloads.", "suggested_fix": "Use parameterized queries by passing email as a tuple argument to cur.execute(query, (email,)) and remove the f-string interpolation."}, {"file": "api/repositories/users.py", "line": 14, "severity": "major", "issue": "The query returns raw database rows (tuple) instead of a User domain object or None, which violates the acceptance criterion 'returns exactly one user' and breaks type expectations for callers like signup_service.", "suggested_fix": "Map the row to a User model instance or return None if row is None."}], "summary": "Critical SQL injection found due to string interpolation. Also returns raw DB rows instead of domain objects, breaking API contracts."}

## Stage output: release_note
{"title": "Exclude soft-deleted users in email lookups", "summary": "The system now filters out soft-deleted users when performing active user lookups by email. This change prevents false duplicate-account warnings for new signups.", "changes": ["Soft-deleted users are excluded from results returned by the active user lookup endpoint when filtering by email."], "breaking": false, "upgrade_notes": ""}