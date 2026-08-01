"""OpenAI provider — config-driven optimization with caching and metrics.

Demonstrates:
- custom `TokenOptConfig` (compression, caching, routing)
- the same call twice to show the in-memory cache hit on the second request
- readable per-request metrics (attempted vs effective compression)

Run with an OpenAI API key:

    export OPENAI_API_KEY=sk-...          # macOS/Linux
    $env:OPENAI_API_KEY = "sk-..."        # PowerShell
"""

from _format import print_request, print_summary, quiet

from tokenopt import OpenAI, TokenOptConfig

config = TokenOptConfig(
    compression_ratio=0.5,
    cache_enabled=True,
    cache_ttl=3600,
    enable_routing=True,
    enable_summarization=True,
    summarization_threshold=8000,
)

client = OpenAI(config=config)
quiet()

messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {
        "role": "user",
        "content": (
            "Give me a detailed summary of the differences between prompt "
            "compression, conversation summarization, and semantic caching "
            "when applied to LLM requests."
        ),
    },
]

# Request 1: fresh call (cache miss)
first = client.chat.completions.create(model="gpt-4o", messages=messages)
print_request(
    client.metrics_collector.get_recent(1)[0],
    response=first.choices[0].message.content,
)
print()

# Request 2: identical call -> served from the in-memory cache (cache hit)
second = client.chat.completions.create(model="gpt-4o", messages=messages)
print_request(
    client.metrics_collector.get_recent(1)[0],
    response=second.choices[0].message.content,
)
print()

print_summary(client.get_metrics_summary())
