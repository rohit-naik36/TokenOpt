"""TokenOpt quick start — drop-in OpenAI replacement.

Demonstrates:
- drop-in usage: the only change from `openai.OpenAI` is the import
- automatic optimization: the prompt is compressed before it reaches the model
- per-request metrics: what the pipeline did, and what it cost you

Expected outcome:
One request, sent through the full pipeline; the printed metrics show the
compression results, the latency split (model vs TokenOpt overhead), and the
estimated cost.

Run with an OpenAI API key:

    export OPENAI_API_KEY=sk-...          # macOS/Linux
    $env:OPENAI_API_KEY = "sk-..."        # PowerShell

Optionally point at any OpenAI-compatible endpoint:

    export OPENAI_BASE_URL=https://my-gateway/v1
"""

from _format import explain, print_request, print_summary, quiet

from tokenopt import OpenAI

client = OpenAI()
quiet()  # keep the console clean; structured JSON stays available for production

# A realistic prompt: an email-style question with filler words, so the
# compressor has something to remove before the model is charged for it.
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "You are a concise assistant."},
        {
            "role": "user",
            "content": (
                "Could you please explain, in a few sentences, how semantic "
                "caching works in LLM applications? It basically stores "
                "previous responses and reuses them when the same or a very "
                "similar prompt comes in again, which I believe can save money "
                "and reduce latency, and I was wondering how that interacts "
                "with prompt compression and conversation summarization in "
                "the same pipeline, and whether it is in your opinion safe "
                "to use in production workloads."
            ),
        },
    ],
)

# Latest request's metrics, rendered readably
print_request(
    client.metrics_collector.get_recent(1)[0],
    response=response.choices[0].message.content,
)
print()
explain(client.metrics_collector.get_recent(1)[0])
print()
print_summary(client.get_metrics_summary())
