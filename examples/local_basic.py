"""Local provider — Ollama, vLLM, llama.cpp, or LM Studio.

The backend is auto-detected from `base_url`:

- ``http://localhost:11434`` (Ollama default) -> native `ollama` package
  (requires the `[local]` extra: `pip install -e ".[local]"`)
- any other URL -> OpenAI-compatible `/v1` endpoint
  (vLLM, llama.cpp, LM Studio — no extra needed)

Override the endpoint for validation or custom setups:

    export TOKENOPT_EXAMPLE_BASE_URL=http://localhost:8000/v1
"""

import os

from _format import print_request, print_summary, quiet

from tokenopt import LocalClient

base_url = os.environ.get("TOKENOPT_EXAMPLE_BASE_URL", "http://localhost:11434")

client = LocalClient(model="llama3.1", base_url=base_url)
quiet()

messages = [{"role": "user", "content": "Hello! Who are you?"}]

# Request 1: first time this prompt is seen -> cache miss, API call made
first = client.chat.completions.create(messages=messages)
print_request(
    client.metrics_collector.get_recent(1)[0],
    response=first.choices[0].message.content,
)
print()

# Request 2: identical prompt, same client -> cache hit, no API call
second = client.chat.completions.create(messages=messages)
print_request(
    client.metrics_collector.get_recent(1)[0],
    response=second.choices[0].message.content,
)
print()

print("Note: the in-memory cache lives on the client instance.")
print("It does NOT persist across separate program executions.")
print()

print_summary(client.get_metrics_summary())
