"""Optimization pipeline — routing rules, RAG, and few-shot configuration.

Demonstrates the configurable stages:
- custom routing rules (model choice depends on the query)
- RAG chunk optimization and few-shot selection
- `create_client` / `create_client_from_model` for provider auto-detection

Run with an OpenAI API key:

    export OPENAI_API_KEY=sk-...          # macOS/Linux
    $env:OPENAI_API_KEY = "sk-..."        # PowerShell
"""

from tokenopt import RoutingRule, TokenOptConfig, create_client_from_model


def is_math_query(query: str, messages: list[dict]) -> bool:
    return any(token in query.lower() for token in ("math", "equation", "integral", "derivative"))


config = TokenOptConfig(
    enable_routing=True,
    routing_rules=[
        RoutingRule(
            name="math_tasks",
            condition=is_math_query,
            model="o1-mini",          # strong reasoning model
            priority=10,
        ),
    ],
    default_model="gpt-4o-mini",      # cheap default when no rule matches
    rag_max_chunks=5,
    fewshot_max_examples=3,
    fewshot_selection_strategy="similarity",
)

client = create_client_from_model("gpt-4o", api_key=None, config=config)

for prompt in ["Explain quantum entanglement simply.", "Solve the equation x^2 = 49."]:
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
    )
    print(f"Prompt: {prompt}")
    print(f"Model used: {response.model}")
    print(f"Answer: {response.choices[0].message.content}")
    print()

print("Optimization usage:", client.get_metrics_summary()["optimization_usage"])
