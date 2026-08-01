"""TokenOpt quick start — drop-in OpenAI replacement.

Run with an OpenAI API key:

    export OPENAI_API_KEY=sk-...          # macOS/Linux
    $env:OPENAI_API_KEY = "sk-..."        # PowerShell

Optionally point at any OpenAI-compatible endpoint:

    export OPENAI_BASE_URL=https://my-gateway/v1

The rest of the code is identical to using `openai.OpenAI` directly.
"""

from _format import print_request, print_summary, quiet

from tokenopt import OpenAI

client = OpenAI()
quiet()  # keep the console clean; structured JSON stays available for production

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "You are a concise assistant."},
        {"role": "user", "content": "Explain what TokenOpt does in one sentence."},
    ],
)

# Latest request's metrics, rendered readably
print_request(
    client.metrics_collector.get_recent(1)[0],
    response=response.choices[0].message.content,
)
print()
print_summary(client.get_metrics_summary())
