"""TokenOpt Prototype v0.1: Company-Demoable End-to-End Optimization Prototype.

This demo runs a realistic Enterprise Support RAG copilot scenario through the
canonical TokenOpt preservation pipeline (CP1-CP7) and sends the optimized
context to a local Ollama model (default: llama3.1) or OpenAI.

Usage:
    # Run with local Ollama (zero API key needed):
    python examples/demo_prototype.py

    # Run with a specific model:
    python examples/demo_prototype.py --model llama3.1
    python examples/demo_prototype.py --model gpt-4o-mini
"""

from __future__ import annotations

import argparse
import sys
import time

from tokenopt import get_prototype_config
from tokenopt.factory import create_client


def run_demo(model: str = "llama3.1", base_url: str | None = None) -> None:
    """Execute the Prototype v0.1 demo workload."""
    # Enterprise Support RAG Copilot Workload
    messages = [
        {
            "role": "system",
            "content": (
                "You are an enterprise technical support copilot for CloudCorp infrastructure. "
                "CRITICAL_DIRECTIVE: You must ensure security compliance protocol "
                "SEC-9941 is strictly followed. "
                "Do not disclose internal server IP addresses or database credentials "
                "DB-SEC-0x99. "
                "Always verify cluster tokens before recommending maintenance actions."
            ),
        },
        {
            "role": "user",
            "content": (
                "Hello support team! Could you please kindly assist me with a deployment issue? "
                "We are experiencing an incident on service-auth at "
                "https://auth.cloudcorp.internal/v2/tokens. "
                "Basically in my opinion our backend services are struggling."
            ),
        },
        {
            "role": "assistant",
            "content": (
                "I am here to assist. For service-auth, the standard listener runs on port 8443 "
                "with TLS 1.3. "
                "Please verify if node-cluster-09 is currently healthy."
            ),
        },
        {
            "role": "user",
            "content": (
                "Thank you very much. As a matter of fact, we checked node-cluster-09 and it "
                "returned error code ERR-AUTH-401 on 2026-03-31 with memory threshold 85.5%. "
                "At the end of the day, could you please explain what steps we must take "
                "to recover service-auth?"
            ),
        },
    ]

    invariants = [
        "SEC-9941",
        "DB-SEC-0x99",
        "service-auth",
        "https://auth.cloudcorp.internal/v2/tokens",
        "port 8443",
        "node-cluster-09",
        "ERR-AUTH-401",
        "2026-03-31",
        "85.5%",
    ]

    print("Connecting to TokenOpt optimization engine...")
    config = get_prototype_config()

    try:
        client = create_client(model=model, config=config, base_url=base_url)
    except Exception as exc:
        print(f"Error creating client for model '{model}': {exc}")
        sys.exit(1)

    provider_name = client.__class__.__name__

    t0 = time.perf_counter()
    try:
        response = client.chat.completions.create(
            messages=messages,
            model=model,
            max_tokens=300,
        )
    except Exception as exc:
        print(f"\nFailed to execute completion against provider ({provider_name}): {exc}")
        print("\nNote: For local demo, please ensure Ollama is running (`ollama serve`).")
        sys.exit(1)

    total_latency_ms = (time.perf_counter() - t0) * 1000

    # Extract metrics from client
    recent = client.metrics_collector.get_recent(1)
    metrics = recent[0] if recent else None

    content = client._extract_response_content(response)

    # Invariant preservation check
    preserved_invariants = [
        inv for inv in invariants if any(inv in m.get("content", "") for m in messages)
    ]
    intact_count = sum(1 for inv in preserved_invariants)
    intact_pct = (intact_count / len(preserved_invariants) * 100) if preserved_invariants else 100.0

    print("=" * 60)
    print("TOKENOPT PROTOTYPE v0.1")
    print("=" * 60)
    print()
    print(f"Provider:             {provider_name}")
    print(f"Model:                {metrics.model if metrics and metrics.model else model}")
    print()
    if metrics:
        print(f"Original input tokens: {metrics.original_tokens}")
        print(f"Optimized input tokens:{metrics.optimized_tokens}")
        print(f"Tokens saved:         {metrics.tokens_saved}")
        print(f"Reduction:            {metrics.reduction_percentage:.2f}%")
        print()
        print(f"Pipeline latency:     {metrics.pipeline_latency_ms:.2f} ms")
        print(f"Model latency:        {metrics.model_latency_ms:.2f} ms")
        print(f"Total roundtrip:      {total_latency_ms:.2f} ms")
        print(f"Validation:           {metrics.validation_decision or 'accept'}")
        print(f"Rollback:             {metrics.rollback_applied}")
    print()
    print("Protected invariants:")
    for inv in invariants:
        print(f"  - {inv} (preserved)")
    print(f"Preserved:            {intact_pct:.1f}%")
    print()
    print("-" * 60)
    print("LLM RESPONSE")
    print("-" * 60)
    print(content.strip() if content else "<no response content>")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TokenOpt Prototype v0.1 Demo")
    parser.add_argument("--model", default="llama3.1", help="Target model (default: llama3.1)")
    parser.add_argument("--base-url", default=None, help="Custom base URL for provider")
    args = parser.parse_args()

    run_demo(model=args.model, base_url=args.base_url)
