"""Local provider — Ollama, vLLM, llama.cpp, or LM Studio.

Demonstrates:
- local support: the same optimization pipeline (compression, caching,
  metrics) runs against locally served models, not just cloud APIs
- backend auto-detection from `base_url` (Ollama vs OpenAI-compatible)
- semantic caching on a local model: a repeat request is served from the
  in-memory cache with no inference call
- cloud routing rules are skipped for local backends (see comment below)

Expected outcome:
A multi-paragraph code-review prompt compressed before the local model sees
it, then a second identical request served from the cache (~1 ms, no model
call). Metrics and cost estimation work exactly as for cloud providers.

Override the endpoint for validation or custom setups:

    export TOKENOPT_EXAMPLE_BASE_URL=http://localhost:8000/v1

Backends:
- ``http://localhost:11434`` (Ollama default) -> native `ollama` package
  (requires the `[local]` extra: `pip install -e ".[local]"`)
- any other URL -> OpenAI-compatible `/v1` endpoint
  (vLLM, llama.cpp, LM Studio — no extra needed)
"""

import os

from _format import explain, print_request, print_summary, quiet

from tokenopt import LocalClient

base_url = os.environ.get("TOKENOPT_EXAMPLE_BASE_URL", "http://localhost:11434")

# Note: routing rules that target cloud models (gpt-*, claude-*, o1-*) are
# automatically excluded for local backends — a local server can only be
# routed to models it actually serves. Compression and caching apply
# unchanged, so local workloads still get the same savings.
client = LocalClient(model="llama3.1", base_url=base_url)
quiet()

# A realistic multi-paragraph prompt with filler words: a code-review request.
messages = [{
    "role": "user",
    "content": (
        "Please review the following Python function and tell me if it is "
        "correct. I basically wrote it to normalize user input for a search "
        "index: it takes a string, lowercases it, strips leading and "
        "trailing whitespace, removes duplicate spaces, and then strips a "
        "few punctuation characters. I believe there is a subtle bug when "
        "the input contains unicode, and also when it is empty, and I would "
        "kindly like you to point out any edge cases I missed, suggest "
        "improvements for performance, and confirm whether using regex here "
        "is reasonable or if a simple character filter would be better. "
        "Here is the code: def normalize(text): import re; text = "
        "text.strip().lower(); text = re.sub(r'\\s+', ' ', text); return "
        "text.rstrip(',.!?')  # please double-check this."
    ),
}]

# Request 1: first time this prompt is seen -> cache miss, API call made
first = client.chat.completions.create(messages=messages)
print_request(
    client.metrics_collector.get_recent(1)[0],
    response=first.choices[0].message.content,
)
print()
explain(client.metrics_collector.get_recent(1)[0])
print()

# Request 2: identical prompt, same client -> cache hit, no API call
second = client.chat.completions.create(messages=messages)
print_request(
    client.metrics_collector.get_recent(1)[0],
    response=second.choices[0].message.content,
)
print()
explain(client.metrics_collector.get_recent(1)[0])
print()

print("Note: the in-memory cache lives on the client instance.")
print("It does NOT persist across separate program executions.")
print()

print_summary(client.get_metrics_summary())
