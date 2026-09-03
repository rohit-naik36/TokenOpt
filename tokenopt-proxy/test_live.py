"""Live end-to-end smoke test for the TokenOpt platform.

This script boots the real app (including its startup lifecycle so providers
register), generates a JWT login token, and exercises:
  1. /health                          - server alive
  2. /v1/tokenopt/validate            - real prompt compression (token savings)
  3. /v1/chat/completions (sync)     - real OpenAI-backed chat
  4. /v1/chat/completions (stream)   - real OpenAI-backed streaming chat

SECURITY: The OpenAI key is NOT stored in this file. It is read from the
environment variable OPENAI_API_KEY, which you set before running:

    $env:OPENAI_API_KEY = "your-fresh-key"      # PowerShell
    export OPENAI_API_KEY="your-fresh-key"       # bash

No real secrets should ever be committed to source control.
"""

import os
import sys
import time

import jwt as pyjwt
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tokenopt_proxy_v2 as proxy

KEY = os.getenv("OPENAI_API_KEY", "").strip()
if not KEY:
    if __name__ != "__main__":
        import pytest

        pytest.skip("OPENAI_API_KEY not set; skipping live smoke test", allow_module_level=True)
    print("ERROR: OPENAI_API_KEY environment variable is not set.")
    print("Set it first, e.g.:")
    print('    $env:OPENAI_API_KEY = "your-fresh-key"')
    sys.exit(1)

# Derive a stable local JWT secret so we can mint a login token for the test.
LOCAL_JWT = os.getenv("JWT_SECRET", "").strip() or ("x" * 40)

MODEL = os.getenv("TOKENOPT_TEST_MODEL", "gpt-4")

# A reasonably long, compressible prompt so the editor has something to shrink.
LONG_PROMPT = (
    "Write a detailed five-paragraph essay explaining the history of the "
    "printing press and its profound impact on literacy rates and the "
    "spread of knowledge across Europe during the Renaissance period, "
    "covering key inventors, technological innovations, and social changes."
)


def mint_token() -> str:
    payload = {
        "tenant_id": "test-tenant",
        "sub": "test-user",
        "roles": ["admin"],
        "plan": "enterprise",
        "exp": int(time.time()) + 3600,
    }
    return pyjwt.encode(payload, LOCAL_JWT, algorithm="HS256")


def main() -> int:
    failures = 0

    # Load the key into config before startup so the provider registers.
    proxy.services.config.OPENAI_API_KEY = KEY
    proxy.services.config.JWT_SECRET = LOCAL_JWT

    results = []
    with TestClient(proxy.app, raise_server_exceptions=False) as client:
        headers = {"Authorization": f"Bearer {mint_token()}"}

        # 1. Health
        r = client.get("/health")
        ok = r.status_code == 200
        results.append(("health", ok, r.status_code, None))
        if not ok:
            failures += 1

        # 2. Validate (prompt compression)
        r = client.post(
            "/v1/tokenopt/validate",
            params={"prompt": LONG_PROMPT},
            headers=headers,
        )
        detail = None
        ok = r.status_code == 200
        if ok:
            body = r.json()
            detail = {
                "savings_pct": body.get("savings_pct"),
                "original_tokens": body.get("original_tokens"),
                "optimized_tokens": body.get("optimized_tokens"),
            }
        else:
            failures += 1
        results.append(("validate", ok, r.status_code, detail))

        # 3. Chat (sync)
        r = client.post(
            "/v1/chat/completions",
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": LONG_PROMPT}],
            },
            headers=headers,
        )
        detail = None
        if r.status_code == 200:
            body = r.json()
            tok = body.get("tokenopt", {})
            detail = {
                "savings_pct": tok.get("savings_pct"),
                "fidelity_passed": tok.get("fidelity_passed"),
                "content_len": len(body.get("choices", [{}])[0].get("message", {}).get("content", "") or ""),
            }
        ok = r.status_code == 200
        if not ok:
            failures += 1
        results.append(("chat_sync", ok, r.status_code, detail))

        # 4. Chat (stream)
        r = client.post(
            "/v1/chat/completions",
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": LONG_PROMPT}],
                "stream": True,
            },
            headers=headers,
        )
        detail = None
        if r.status_code == 200:
            detail = {"content_type": r.headers.get("content-type"), "bytes": len(r.content)}
        ok = r.status_code == 200
        if not ok:
            failures += 1
        results.append(("chat_stream", ok, r.status_code, detail))

    print("\n===== RESULTS =====")
    for name, ok, status, detail in results:
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name}: status={status}")
        if detail:
            print(f"        {detail}")

    print("\n===== OVERALL =====")
    if failures == 0:
        print("ALL CHECKS PASSED")
        return 0
    print(f"{failures} CHECK(S) FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
