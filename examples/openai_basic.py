"""OpenAI provider — compression: OFF vs ON, then a cache hit.

Demonstrates:
- prompt compression as the primary cost saver: the SAME prompt sent through
  a plain client vs a TokenOpt-compressed client (fills/structure removed,
  oversized messages truncated to the target ratio)
- semantic caching as the secondary saver: an identical repeat call skips the
  model entirely (cache hit)
- honest metrics: attempted vs effective compression, tokens saved, latency
  split, and estimated cost

Expected outcome:
A before/after comparison showing ~44% fewer tokens with compression enabled,
then a second identical request served from the in-memory cache in ~1 ms of
TokenOpt overhead with no model call at all.

Run with an OpenAI API key:

    export OPENAI_API_KEY=sk-...          # macOS/Linux
    $env:OPENAI_API_KEY = "sk-..."        # PowerShell
"""

from _format import explain, print_comparison, print_request, print_summary, quiet

from tokenopt import OpenAI, TokenOptConfig

quiet()  # keep the console clean; structured JSON stays available for production

# A deliberately long, verbose prompt (~400 words): a status report written by
# someone in a hurry, full of filler words and padded structure. This is what
# the compressor is for — you should not have to write tighter prompts.
LONG_PROMPT = (
    "Please review the attached architecture document for our payment "
    "microservices platform and provide a detailed assessment. I believe the "
    "system currently consists of basically four main services: the gateway, "
    "the auth service, the transaction processor, and the settlement worker. "
    "The gateway is responsible for receiving incoming requests, and I think "
    "it should validate API keys, apply rate limits, and then route the "
    "request to the appropriate downstream service. The auth service handles "
    "tokens, sessions, and password resets, and in my opinion it could "
    "probably benefit from a dedicated read replica because the read-to-write "
    "ratio is quite high. The transaction processor performs the actual "
    "payment operations, and essentially it needs to be idempotent, so that "
    "retries do not double-charge customers, which I believe is a common "
    "source of production incidents. The settlement worker aggregates "
    "transactions and pushes them to the bank in batches, and fundamentally "
    "its scheduling logic is overdue for a rewrite because the current "
    "cron-based approach does not handle backpressure well. Overall I would "
    "kindly ask you to focus your review on failure handling, idempotency, "
    "observability, and the database schema for the transaction store, and "
    "please include concrete recommendations with priorities. Also, if you "
    "could comment on the queue choice, I think RabbitMQ is probably fine "
    "but I have seen arguments for Kafka, and I would really appreciate your "
    "opinion on the tradeoffs before we finalize the design. Finally, please "
    "double-check the scaling story: the platform should handle a tenfold "
    "traffic increase during the holiday season, and I want to make sure the "
    "proposed pod autoscaling and connection pool settings are adequate."
)

# --- Section 1: compression OFF vs ON ------------------------------------
# "Before TokenOpt": a plain configuration with every optimization disabled.
# The prompt goes to the model exactly as written.
plain_config = TokenOptConfig(
    enable_compression=False,
    cache_enabled=False,
    enable_routing=False,
    enable_summarization=False,
)
plain_client = OpenAI(config=plain_config)

# "After TokenOpt": same prompt, but compression is enabled (50% target).
# Fillers are removed; the oversized message is truncated to the budget.
compressed_config = TokenOptConfig(
    compression_ratio=0.5,
    cache_enabled=False,
    enable_routing=False,
    enable_summarization=False,
)
compressed_client = OpenAI(config=compressed_config)

messages = [
    {"role": "system", "content": "You are a senior software architect."},
    {"role": "user", "content": LONG_PROMPT},
]

plain_client.chat.completions.create(model="gpt-4o", messages=messages)
compressed_client.chat.completions.create(model="gpt-4o", messages=messages)

print_comparison(
    "Compression OFF vs ON (identical prompt):",
    plain_client.metrics_collector.get_recent(1)[0],
    compressed_client.metrics_collector.get_recent(1)[0],
)
print()
explain(compressed_client.metrics_collector.get_recent(1)[0])
print()

# --- Section 2: cache miss -> hit ----------------------------------------
# New client with caching enabled. The same compressed prompt is sent twice:
# the first call misses, the second is served from the in-memory cache.
cached_config = TokenOptConfig(
    cache_enabled=True,
    cache_ttl=3600,
    enable_routing=False,
)
cached_client = OpenAI(config=cached_config)

first = cached_client.chat.completions.create(model="gpt-4o", messages=messages)
print_request(
    cached_client.metrics_collector.get_recent(1)[0],
    response=first.choices[0].message.content,
)
print()

second = cached_client.chat.completions.create(model="gpt-4o", messages=messages)
print_request(
    cached_client.metrics_collector.get_recent(1)[0],
    response=second.choices[0].message.content,
)
print()
explain(cached_client.metrics_collector.get_recent(1)[0])
print()

print_summary(cached_client.get_metrics_summary())
