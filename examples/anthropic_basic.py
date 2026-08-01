"""Anthropic provider — drop-in replacement with summarization.

Demonstrates:
- provider compatibility: `tokenopt.Anthropic` mirrors the official SDK's
  call surface (`client.messages.create`, `max_tokens`, ...) — one import
  change and the same optimization pipeline applies
- conversation summarization: when the history exceeds the configured token
  threshold, older turns are condensed into a summary instead of being sent
  verbatim, keeping long conversations cheap and within the context window
- compression applies to Claude requests exactly as it does to OpenAI's

Expected outcome:
A 5-turn conversation that overflows the (deliberately low) 150-token
threshold: the first turns are summarized, the recent ones pass through, and
the metrics show the history shrank below the budget.

Run with an Anthropic API key:

    export ANTHROPIC_API_KEY=sk-ant-...   # macOS/Linux
    $env:ANTHROPIC_API_KEY = "sk-ant-..." # PowerShell
"""

from _format import explain, print_request, print_summary, quiet

from tokenopt import Anthropic, TokenOptConfig

# Threshold lowered to 150 tokens so a short conversation triggers
# summarization. The default (8000) is for production-scale histories.
config = TokenOptConfig(
    enable_summarization=True,
    summarization_threshold=150,
    enable_compression=True,
    cache_enabled=False,
    enable_routing=False,
)

client = Anthropic(config=config)
quiet()

# A natural multi-turn conversation. The first user turn is a long question,
# the assistant answers, and the follow-ups refine it. Together the turns
# far exceed the 150-token threshold.
conversation = [
    {"role": "user", "content": (
        "Please explain how TokenOpt decides which requests get compressed, "
        "which get summarized, and which get cached — I want to understand "
        "the order the optimization stages run in and how they interact."
    )},
    {"role": "assistant", "content": (
        "Each request passes through a pipeline: routing, compression, "
        "summarization, caching, RAG, and few-shot selection, in that order."
    )},
    {"role": "user", "content": (
        "Thanks, that helps. So compression runs before caching — does that "
        "mean two differently-phrased prompts that compress to the same text "
        "will actually hit the same cache entry?"
    )},
    {"role": "assistant", "content": (
        "Yes. The cache keys on the optimized messages, so the same compressed "
        "form is the same cache entry."
    )},
    {"role": "user", "content": (
        "Great, and can I disable individual stages without losing the "
        "others — like keep caching but turn compression off?"
    )},
]

response = client.messages.create(
    model="claude-3-5-haiku",
    max_tokens=1024,
    messages=conversation,
)

# The metrics show original vs optimized tokens: the first two turns were
# replaced by a compact "Previous conversation summary" system message.
print_request(
    client.metrics_collector.get_recent(1)[0],
    response="".join(block.text for block in response.content),
)
print()
explain(client.metrics_collector.get_recent(1)[0])
print()
print_summary(client.get_metrics_summary())
