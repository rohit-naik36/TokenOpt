"""
TokenOpt Demo Script
====================
Run this during your Monday presentation.

SETUP (2 min before the meeting):
1. Get a free Gemini key at https://aistudio.google.com → "Get API Key"
2. Run:
      set GEMINI_API_KEY=your-key-here
      set JWT_SECRET=demo-secret-key-for-presentation-only
      python demo.py

OR for the validate-only demo (zero API keys needed):
      set JWT_SECRET=demo-secret-key-for-presentation-only
      python demo.py --no-llm
"""

import asyncio
import json
import os
import sys
import time
import httpx
import jwt
from datetime import datetime, timezone, timedelta

BASE_URL = "http://localhost:8000"
JWT_SECRET = os.getenv("JWT_SECRET", "demo-secret-key-for-presentation-only")
NO_LLM = "--no-llm" in sys.argv

# --------------------------------------------------------------------------
# Demo prompts — chosen to show dramatic savings on realistic enterprise text
# --------------------------------------------------------------------------
DEMO_PROMPTS = [
    {
        "label": "Verbose Support Ticket",
        "text": (
            "I am writing to you today because I am experiencing a rather significant "
            "issue with the software that I have been using. Basically, essentially what "
            "is happening is that the system is actually crashing quite frequently, and "
            "I would really appreciate it if you could please take the time to look into "
            "this matter for me, in order to resolve it as quickly as possible, due to "
            "the fact that it is causing me a great deal of frustration at this point in time."
        ),
    },
    {
        "label": "Enterprise System Prompt",
        "text": (
            "You are an AI assistant that has been specifically designed for the purpose of "
            "helping enterprise users with their daily tasks. It is important to note that "
            "you should always be professional and courteous in all of your responses. "
            "Please note that you should never provide information that could be considered "
            "harmful or inappropriate. In the event that a user asks something outside your "
            "scope, it should be noted that you should politely redirect them."
        ),
    },
    {
        "label": "Meeting Summary Request",
        "text": (
            "Due to the fact that we had a rather lengthy meeting earlier today, I would "
            "really like you to help me create a summary of the key points that were "
            "discussed in order to share with team members who were not able to attend. "
            "In spite of the fact that there were quite a few topics covered, the most "
            "fundamentally important ones were related to the Q3 budget and the new "
            "product roadmap that was essentially presented by the CTO."
        ),
    },
]


def make_token(tenant_id: str = "demo-corp") -> str:
    payload = {
        "tenant_id": tenant_id,
        "sub": tenant_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def separator(title: str = ""):
    width = 65
    if title:
        pad = (width - len(title) - 2) // 2
        print(f"\n{'─' * pad} {title} {'─' * pad}")
    else:
        print(f"\n{'─' * width}")


def print_optimization_result(result: dict):
    orig = result.get("original_tokens", 0)
    opt  = result.get("optimized_tokens", 0)
    pct  = result.get("savings_pct", 0)
    fid  = result.get("fidelity_score")
    techniques = result.get("techniques", [])
    passed = result.get("fidelity_passed", True)

    print(f"  Original tokens : {orig}")
    print(f"  Optimized tokens: {opt}  ({pct:.1f}% savings ✅)" if pct > 0 else f"  Optimized tokens: {opt}")
    if fid is not None:
        emoji = "✅" if passed else "⚠️ "
        print(f"  Fidelity score  : {fid:.4f} {emoji}")
    if techniques:
        print(f"  Techniques      : {', '.join(techniques)}")
    if result.get("original"):
        print(f"\n  BEFORE: {result['original'][:120]}...")
        print(f"  AFTER : {result['optimized'][:120]}...")


async def demo_validate_only(client: httpx.AsyncClient, token: str):
    """
    Part 1 — No LLM needed.
    Shows the optimization pipeline, token savings, and fidelity scoring
    using the /v1/tokenopt/validate endpoint.
    """
    separator("PART 1: Optimization Preview (no LLM needed)")
    print("  Endpoint: POST /v1/tokenopt/validate")
    print("  What it does: Shows exactly what TokenOpt would send to the LLM,")
    print("  and the projected token savings — without actually calling it.\n")

    for prompt_data in DEMO_PROMPTS:
        print(f"\n  [{prompt_data['label']}]")
        resp = await client.post(
            f"{BASE_URL}/v1/tokenopt/validate",
            params={"prompt": prompt_data["text"]},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15.0,
        )
        if resp.status_code == 200:
            print_optimization_result(resp.json())
        else:
            print(f"  ⚠️  {resp.status_code}: {resp.text[:200]}")
        await asyncio.sleep(0.3)


async def demo_live_call(client: httpx.AsyncClient, token: str):
    """
    Part 2 — Requires GEMINI_API_KEY.
    Makes a real optimized LLM call and shows the tokenopt metadata block
    attached to the response.
    """
    separator("PART 2: Live Optimized LLM Call")
    print("  Endpoint: POST /v1/chat/completions")
    print("  Model   : gemini-2.0-flash (free tier)\n")

    prompt = DEMO_PROMPTS[0]
    print(f"  Sending: [{prompt['label']}]")
    print(f"  Input  : {prompt['text'][:80]}...\n")

    payload = {
        "model": "gemini-2.0-flash",
        "messages": [{"role": "user", "content": prompt["text"]}],
        "optimization_level": "standard",
    }

    t0 = time.perf_counter()
    resp = await client.post(
        f"{BASE_URL}/v1/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )
    elapsed = time.perf_counter() - t0

    if resp.status_code == 200:
        data = resp.json()
        tokenopt = data.get("tokenopt", {})
        reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        print(f"  ✅ Response received in {elapsed:.2f}s")
        print(f"\n  LLM Reply: {reply[:200]}")
        separator("TokenOpt Metadata (attached to every response)")
        print(json.dumps(tokenopt, indent=4))
    else:
        print(f"  ❌ {resp.status_code}: {resp.text[:300]}")


async def demo_health(client: httpx.AsyncClient):
    separator("PART 0: Service Health")
    resp = await client.get(f"{BASE_URL}/health", timeout=5.0)
    if resp.status_code == 200:
        data = resp.json()
        print(f"  Status  : {data.get('status', '?').upper()} ✅")
        print(f"  Version : {data.get('version', '?')}")
        svcs = data.get("services", {})
        for name, info in svcs.items():
            status = info.get("status", "?") if isinstance(info, dict) else info
            print(f"  {name:12}: {status}")
    else:
        print(f"  ❌ Health check failed: {resp.status_code}")


async def main():
    print("\n" + "═" * 65)
    print("  TokenOpt Enterprise v2.0 — Live Demo")
    print("  " + datetime.now().strftime("%A, %B %d %Y  %H:%M"))
    print("═" * 65)

    # Pre-flight: check JWT_SECRET is set
    if not os.getenv("JWT_SECRET"):
        print("\n  ❌ JWT_SECRET environment variable is not set.")
        print("     The server won't authenticate requests without it.\n")
        print("     Fix — run these before starting the server AND this script:")
        print("       $env:JWT_SECRET='demo-secret-key-for-presentation-only'")
        print("       $env:JWT_SECRET='demo-secret-key-for-presentation-only'  # server terminal too\n")
        print("     Then restart the server:  uvicorn tokenopt_proxy_v2:app --port 8000")
        print("     Then re-run:              python demo.py --no-llm\n")
        sys.exit(1)

    token = make_token()

    # Verify the server is running
    try:
        async with httpx.AsyncClient() as client:
            await client.get(f"{BASE_URL}/health", timeout=3.0)
    except Exception:
        print("\n  ❌ Server is not running. Start it first with:")
        print("       uvicorn tokenopt_proxy_v2:app --host 0.0.0.0 --port 8000")
        print("     Then run this script again.\n")
        sys.exit(1)

    async with httpx.AsyncClient() as client:
        await demo_health(client)
        await demo_validate_only(client, token)

        if not NO_LLM:
            if os.getenv("GEMINI_API_KEY"):
                await demo_live_call(client, token)
            else:
                separator("PART 2: Live LLM Call — SKIPPED")
                print("  Set GEMINI_API_KEY to enable live calls.")
                print("  Get a free key at: https://aistudio.google.com")

    separator()
    print("\n  Demo complete. Key takeaways:")
    print("  • Optimization runs BEFORE the LLM call — zero response quality impact")
    print("  • Fidelity guard automatically rolls back if meaning would be lost")
    print("  • Every call gets a tokenopt block: tokens saved, cost saved, techniques used")
    print("  • Transparent proxy — existing code needs zero changes\n")


if __name__ == "__main__":
    asyncio.run(main())
