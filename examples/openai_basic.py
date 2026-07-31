"""OpenAI provider — config-driven optimization with caching and metrics.

Demonstrates:
- custom `TokenOptConfig` (compression, caching, routing)
- the same call twice to show the in-memory cache hit on the second request
- reading the aggregated metrics summary

Run with an OpenAI API key:

    export OPENAI_API_KEY=sk-...          # macOS/Linux
    $env:OPENAI_API_KEY = "sk-..."        # PowerShell
"""

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

first = client.chat.completions.create(model="gpt-4o", messages=messages)
print("First call:", first.choices[0].message.content)
print()

second = client.chat.completions.create(model="gpt-4o", messages=messages)
print("Second call (cache hit expected):", second.choices[0].message.content)
print()

summary = client.get_metrics_summary()
print("Requests:", summary["total_requests"])
print("Cache hit rate:", summary["cache_hit_rate"])
print("Avg tokens reduced per request:", summary["avg_token_reduction"])
