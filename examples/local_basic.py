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

from tokenopt import LocalClient

base_url = os.environ.get("TOKENOPT_EXAMPLE_BASE_URL", "http://localhost:11434")

client = LocalClient(model="llama3.1", base_url=base_url)

response = client.chat.completions.create(
    messages=[{"role": "user", "content": "Hello! Who are you?"}],
)

print("Response:", response.choices[0].message.content)
print()
print("Metrics:", client.get_metrics_summary())
