"""Observability — metrics callback, cost estimation, and token utilities.

Demonstrates:
- per-request metrics via a callback (e.g. to push to your own monitoring)
- aggregated summary and estimated cost
- standalone token counting utilities

Run with an OpenAI API key:

    export OPENAI_API_KEY=sk-...          # macOS/Linux
    $env:OPENAI_API_KEY = "sk-..."        # PowerShell
"""

from _format import print_request, print_summary, quiet

from tokenopt import OpenAI, RequestMetrics, TokenOptConfig, count_message_tokens, estimate_cost


def on_request(metrics: RequestMetrics) -> None:
    """Example callback: called once per request with its metrics."""
    print(
        f"  [callback] model={metrics.model} "
        f"tokens={metrics.original_tokens}->{metrics.optimized_tokens} "
        f"(saved {metrics.tokens_saved:+d}) "
        f"routed={metrics.routing_applied} cache_hit={metrics.cache_hit}"
    )


config = TokenOptConfig(metrics_callback=on_request)
client = OpenAI(config=config)
quiet()

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "user", "content": "What are the benefits of semantic caching?"},
    ],
)
print()
print_request(
    client.metrics_collector.get_recent(1)[0],
    response=response.choices[0].message.content,
)
print()
print_summary(client.get_metrics_summary())
print()

# Standalone utilities
messages = [{"role": "user", "content": "Count my tokens"}]
print("Message tokens:", count_message_tokens(messages, "gpt-4o"))
print("Estimated cost (gpt-4o, 100 in / 50 out):", estimate_cost("gpt-4o", 100, 50), "USD")
