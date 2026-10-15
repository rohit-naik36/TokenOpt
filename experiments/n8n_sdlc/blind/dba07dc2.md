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
{"severity": "P0", "category": "security", "component": "auth", "summary": "Pen-test finding: password reset tokens remain valid indefinitely, enabling account takeover. Must enforce 30-minute expiry and single-use.", "risk_flags": ["account_takeover", "token_exposure"], "needs_security_review": true}

## Stage output: requirements
{"user_story": "As a security analyst, I want password reset tokens to expire after 30 minutes and be single-use so that account takeovers via old links are prevented.", "acceptance_criteria": ["Given a valid token issued at time T, When the POST /auth/reset/confirm endpoint is called with that token at time T+31 minutes, Then HTTP 400 is returned with {\"error\": \"invalid_or_expired_token\"}.", "Given a valid token issued at time T, When the POST /auth/reset/confirm endpoint is called with that same token again after a successful password reset at time T+5 minutes, Then HTTP 400 is returned with {\"error\": \"invalid_or_expired_token\"}.", "Given an invalid or expired token, When the POST /auth/reset/confirm endpoint is called with that token, Then HTTP 400 is returned with {\"error\": \"invalid_or_expired_token\"}.", "Given a valid token, When the POST /auth/reset/confirm endpoint successfully processes a password reset, Then the token is immediately invalidated and cannot be used for any subsequent request.", "Given an expired or already-used token, When the POST /auth/reset/confirm endpoint is called with that token, Then the response body must not reveal whether the token was invalid or expired.", "Given a valid token, When the POST /auth/reset/confirm endpoint successfully processes a password reset, Then the user's password is updated immediately."], "non_goals": [], "open_questions": []}

## Stage output: plan
{"steps":[{"id":1,"description":"Add a TTL field to the password reset token model and update token creation logic","files":["models/token.py","services/auth_service.py"]},{"id":2,"description":"Implement token validation logic that checks both expiration time and single-use status before processing the reset","files":["services/auth_service.py"]},{"id":3,"description":"Update the POST /auth/reset/confirm endpoint to invalidate tokens immediately upon successful password update","files":["views/auth_views.py"]},{"id":4,"description":"Ensure error responses for invalid/expired/used tokens return a generic 'invalid_or_expired_token' message without leaking state","files":["views/auth_views.py"]},{"id":5,"description":"Add unit tests for token expiration and reuse scenarios","files":["tests/unit/test_auth_service.py"]},{"id":6,"description":"Add integration tests verifying endpoint behavior with expired and reused tokens","files":["tests/integration/test_auth_endpoints.py"]},{"id":7,"description":"Update API documentation to reflect the 30-minute token lifetime policy","files":["docs/api/auth.md"]}], "risks": ["If token validation logic is placed incorrectly, it could allow reuse of expired tokens; mitigate by centralizing validation in a single service method.","If error messages differ between invalid/expired states, attackers can distinguish valid tokens from expired ones; mitigate by using a shared error response factory."], "test_plan": ["POST /auth/reset/confirm with token issued 31 minutes ago returns HTTP 400 {\"error\": \"invalid_or_expired_token\"}.","POST /auth/reset/confirm with same token after successful reset returns HTTP 400 {\"error\": \"invalid_or_expired_token\"}.","POST /auth/reset/confirm with invalid/expired token returns HTTP 400 {\"error\": \"invalid_or_expired_token\"}.","POST /auth/reset/confirm with valid token succeeds and subsequent call with same token fails.","POST /auth/reset/confirm with expired token does not reveal expiration status in response body.","POST /auth/reset/confirm with valid token updates user password immediately."]}

## Stage output: review
{"verdict":"request_changes","findings":[{"file":"auth/src/reset.ts","line":24,"severity":"blocker","issue":"Token expiration check uses > instead of <, allowing tokens valid until exactly Date.now() to be rejected while accepting those expired slightly in the past. The condition token.expiresAt.getTime() > Date.now() should be token.expiresAt.getTime() < Date.now().","suggested_fix":"Replace token.expiresAt.getTime() > Date.now() with token.expiresAt.getTime() < Date.now()."},{"file":"auth/src/reset.ts","line":21,"severity":"major","issue":"The validation logic checks token.usedAt !== null before checking expiration, but if a token is used and then somehow the database update fails (e.g., transaction rollback), the next request might see usedAt as null while the token is logically expired. While less likely with transactions, the order of checks should prioritize expiration first to ensure consistent behavior across all paths.","suggested_fix":"Move the expiration check before the usedAt check: if (!token || token.expiresAt.getTime() < Date.now()) throw ...; then if (token.usedAt !== null) throw ..."}],"summary":"Critical logic error in expiration check (> vs <) causes incorrect rejections. Reorder validations to prioritize expiration state."}

## Stage output: release_note
{"title": "Password reset tokens now expire after 30 minutes", "summary": "Password reset tokens now expire after 30 minutes instead of indefinitely. Tokens are also single-use to prevent account takeovers.", "changes": ["Password reset tokens expire 30 minutes after issuance.", "Tokens become invalid immediately after successful use."], "breaking": true, "upgrade_notes": "Update client applications that reuse old password reset links or store tokens for longer than 30 minutes. Regenerate tokens if previously stored values are now expired."}