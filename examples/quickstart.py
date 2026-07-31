"""TokenOpt quick start — drop-in OpenAI replacement.

Run with an OpenAI API key:

    export OPENAI_API_KEY=sk-...          # macOS/Linux
    $env:OPENAI_API_KEY = "sk-..."        # PowerShell

Optionally point at any OpenAI-compatible endpoint:

    export OPENAI_BASE_URL=https://my-gateway/v1

The rest of the code is identical to using `openai.OpenAI` directly.
"""

from tokenopt import OpenAI

client = OpenAI()

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "You are a concise assistant."},
        {"role": "user", "content": "Explain what TokenOpt does in one sentence."},
    ],
)

print("Response:", response.choices[0].message.content)
print()
print("Metrics:", client.get_metrics_summary())
