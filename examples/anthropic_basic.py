"""Anthropic provider — drop-in replacement for anthropic.Anthropic.

Run with an Anthropic API key:

    export ANTHROPIC_API_KEY=sk-ant-...   # macOS/Linux
    $env:ANTHROPIC_API_KEY = "sk-ant-..." # PowerShell

The call surface matches the official SDK (`client.messages.create`),
including `max_tokens`, `temperature`, and other request options.
"""

from _format import print_request, print_summary, quiet

from tokenopt import Anthropic

client = Anthropic()
quiet()

response = client.messages.create(
    model="claude-3-5-haiku",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Write a one-line haiku about caching."},
    ],
)

print_request(
    client.metrics_collector.get_recent(1)[0],
    response="".join(block.text for block in response.content),
)
print()
print_summary(client.get_metrics_summary())
