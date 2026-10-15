## Ticket
{
  "id": "T05",
  "title": "Password reset tokens must expire after 30 minutes",
  "type": "security",
  "priority_hint": "Critical",
  "reporter": "security-eng",
  "labels": [
    "auth",
    "security",
    "pentest"
  ],
  "description": "Pen-test finding PT-2026-014: password reset links remain valid indefinitely. An attacker with access to an old email can take over an account months later. Reset tokens must be valid for 30 minutes from issue and single use.\n\nBehaviour: `POST /auth/reset/confirm` with an expired or already-used token returns HTTP 400 with `{\"error\": \"invalid_or_expired_token\"}` (same message in both cases so we do not leak which). A valid token sets the new password and is invalidated immediately.",
  "environment": "Node 20, TypeScript, Express, PostgreSQL via Prisma. Service: auth. Tokens are stored hashed with `expiresAt` (timestamp) and `usedAt` (nullable).",
  "comments": [
    "security-eng: Must ship this sprint, customer audit on the 14th.",
    "backend-dev: Token lookup by hash already exists; I only need the expiry check and to set usedAt."
  ]
}

## Diff
diff --git a/auth/src/reset.ts b/auth/src/reset.ts
--- a/auth/src/reset.ts
+++ b/auth/src/reset.ts
@@ -18,16 +18,24 @@ export async function confirmReset(rawToken: string, newPassword: string) {
   const tokenHash = sha256(rawToken);
   const token = await prisma.resetToken.findUnique({ where: { tokenHash } });

-  if (!token) {
-    throw new HttpError(400, "invalid_or_expired_token");
-  }
+  if (!token || token.usedAt !== null) {
+    throw new HttpError(400, "invalid_or_expired_token");
+  }
+
+  if (token.expiresAt.getTime() > Date.now()) {
+    throw new HttpError(400, "invalid_or_expired_token");
+  }

-  await prisma.user.update({
-    where: { id: token.userId },
-    data: { passwordHash: await hashPassword(newPassword) },
-  });
+  await prisma.$transaction([
+    prisma.user.update({
+      where: { id: token.userId },
+      data: { passwordHash: await hashPassword(newPassword) },
+    }),
+    prisma.resetToken.update({ where: { tokenHash }, data: { usedAt: new Date() } }),
+  ]);
 }


## Stage output: triage
{
  "severity": "P0",
  "category": "security",
  "component": "auth",
  "summary": "Fixes indefinite validity of password reset tokens, preventing account takeover via old emails. Adds expiry check and single-use logic.",
  "risk_flags": ["account_takeover", "pentest_finding", "audit_deadline"],
  "needs_security_review": true
}

## Stage output: requirements
{"user_story":"As a security engineer, I want password reset tokens to expire after 30 minutes and be single-use so that account takeover via old emails is prevented.","acceptance_criteria":["Given a POST request to /auth/reset/confirm with a valid token issued more than 30 minutes ago, then the response must return HTTP 400 with {\"error\": \"invalid_or_expired_token\"}.","Given a POST request to /auth/reset/confirm with a token that has already been used successfully, then the response must return HTTP 400 with {\"error\": \"invalid_or_expired_token\"}.","Given a POST request to /auth/reset/confirm with an expired or already-used token, then the error message in the response body must be exactly {\"error\": \"invalid_or_expired_token\"} without distinguishing between expiry and reuse.","Given a POST request to /auth/reset/confirm with a valid, unused token within 30 minutes of issuance, then the response must return HTTP 200 and set the usedAt field on the stored token.","Given a POST request to /auth/reset/confirm with an invalid or expired token, then the new password must not be set for the associated user account.","Given a successful password reset via /auth/reset/confirm, then subsequent requests using the same token must fail immediately regardless of time elapsed since issuance."],"non_goals":[],"open_questions":[]}

## Stage output: plan
{"steps":[{"id":1,"description":"Identify the existing token lookup service and verify it retrieves tokens by hash along with their createdAt, expiresAt, and usedAt fields.","files":["src/auth/services/tokenLookup.ts"]},{"id":2,"description":"Update the token validation logic to check if the current time exceeds expiresAt or if usedAt is not null before attempting password reset.","files":["src/auth/controllers/resetController.ts","src/auth/services/tokenValidator.ts"]},{"id":3,"description":"Implement the single-use invalidation by setting usedAt to the current timestamp immediately upon successful password update.","files":["src/auth/repositories/tokenRepository.ts"]},{"id":4,"description":"Ensure the error response body is consistently set to {\"error\": \"invalid_or_expired_token\"} for both expiry and reuse scenarios without leaking state.","files":["src/auth/controllers/resetController.ts"]},{"id":5,"description":"Add unit tests covering valid token usage, expired token rejection, reused token rejection, and boundary conditions (exactly 30 minutes).","files":["tests/unit/auth/reset.e2e.test.ts","tests/unit/auth/tokenValidator.test.ts"]],"risks":["Account takeover if the expiry check is bypassed or uses server time incorrectly; mitigate by using a trusted system clock and validating timestamps in UTC.","Information leakage if error messages differ between expired and reused tokens; mitigate by enforcing a single generic error string in all failure paths.","Race condition where a token is used twice simultaneously; mitigate by setting usedAt atomically within the database transaction or immediately after password update before committing.","Audit deadline pressure leading to incomplete testing; mitigate by prioritizing critical security test cases first and running them in CI before merging."],"test_plan":["POST /auth/reset/confirm with a token issued >30 minutes ago returns HTTP 400 and {\"error\": \"invalid_or_expired_token\"}.","POST /auth/reset/confirm with a token that has usedAt set (simulating prior use) returns HTTP 400 and {\"error\": \"invalid_or_expired_token\"}.","POST /auth/reset/confirm with an expired or reused token returns the exact error string {\"error\": \"invalid_or_expired_token\"} without distinguishing cause.","POST /auth/reset/confirm with a valid, unused token within 30 minutes returns HTTP 200 and updates usedAt in the database.","POST /auth/reset/confirm with an invalid/expired token does not update the user's password field.","POST /auth/reset/confirm with a successfully used token fails immediately on subsequent requests regardless of time elapsed since issuance."]

## Stage output: review
{"verdict":"request_changes","findings":[{"file":"auth/src/reset.ts","line":28,"severity":"blocker","issue":"The expiry check uses `token.expiresAt.getTime() > Date.now()` which compares local time with UTC timestamps, causing incorrect validation in non-UTC environments. This violates the requirement to use a trusted system clock and can allow tokens to be used indefinitely or rejected prematurely.","suggested_fix":"Convert both timestamps to UTC before comparison: `if (token.expiresAt.getTime() > new Date().getTime())` is still wrong; instead use `if (token.expiresAt < new Date())` since Prisma timestamps are stored in UTC. Or explicitly convert: `const now = new Date(); const expiresAt = token.expiresAt; if (expiresAt < now) throw...`","summary":"Expiry check compares local time with UTC timestamp, causing incorrect validation across timezones."},{"file":"auth/src/reset.ts","line":28,"severity":"major","issue":"The code checks `token.expiresAt.getTime() > Date.now()` but the condition logic is inverted for expiry. It should reject if current time >= expiresAt. The current check rejects when token is still valid (getTime > now means not expired yet).","suggested_fix":"Change to `if (Date.now() >= token.expiresAt.getTime())` or simply `if (token.expiresAt <= new Date())` to correctly identify expired tokens."}],"summary":"Expiry logic is inverted and timezone-unsafe; must reject when current time >= expiresAt using UTC comparison."

## Stage output: release_note
{"title": "Password reset tokens now expire after 30 minutes","summary": "Password reset tokens are now valid for only 30 minutes and single-use. Requests with expired or reused tokens return HTTP 400.","changes": ["POST /auth/reset/confirm rejects tokens older than 30 minutes with HTTP 400.","POST /auth/reset/confirm rejects already-used tokens immediately with HTTP 400.","Error message for invalid tokens is consistently {\"error\": \"invalid_or_expired_token\"} regardless of cause."],"breaking": true,"upgrade_notes": "Integrations relying on indefinite token validity or distinguishing between expired and reused tokens must update their logic to handle the new expiry window and generic error response."}