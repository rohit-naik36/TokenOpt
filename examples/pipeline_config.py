"""Routing — the right model for every request, with the reason why.

Demonstrates:
- custom routing rules: a math query is routed to a strong reasoning model
  (o1-mini) by an explicit rule
- complexity fallback: requests that match no rule are routed by a keyword
  + length heuristic (low/medium/high), which is reported transparently
- routing_reason: every routed request records WHY that model was chosen
  (rule name, or "complexity-based (low|medium|high)")
- routing OFF vs ON: without TokenOpt you must pick one model for everything;
  with routing on, each query gets an appropriate model automatically

Expected outcome:
Four prompts, four different routing decisions (o1-mini for math, gpt-4o for
code and complex analysis, gpt-4o-mini for simple questions), each printed
with its routing_reason — then the math prompt again with routing disabled,
staying on the single manually-chosen model.

Run with an OpenAI API key:

    export OPENAI_API_KEY=sk-...          # macOS/Linux
    $env:OPENAI_API_KEY = "sk-..."        # PowerShell
"""

from _format import explain, print_comparison, print_request, print_summary, quiet

from tokenopt import OpenAI, RoutingRule, TokenOptConfig, create_client_from_model


def is_math_query(query: str, messages: list[dict]) -> bool:
    """Routing rule condition: true for math-related questions."""
    return any(token in query.lower() for token in ("math", "equation", "integral", "derivative"))


# Custom rules REPLACE the defaults. Requests matched by a rule use its model;
# anything unmatched falls back to complexity-based routing (reported in
# routing_reason). Priority decides which rule wins when several match.
config = TokenOptConfig(
    enable_routing=True,
    routing_rules=[
        RoutingRule(
            name="math_tasks",
            condition=is_math_query,
            model="o1-mini",          # strong reasoning model
            priority=40,              # above the default rules' priorities
        ),
    ],
    default_model="gpt-4o-mini",      # cheap fallback when nothing matches
    cache_enabled=False,
)

client = create_client_from_model("gpt-4o", api_key=None, config=config)
quiet()

prompts = [
    ("Simple question", "What is the capital of France?"),
    ("Code request", "Write a python function that implements binary search."),
    ("Math problem", "Solve the equation x^2 = 49 for x."),
    ("Complex analysis", "Analyze and compare the architecture of this microservices system."),
]

math_metrics = None
for label, prompt in prompts:
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
    )
    metric = client.metrics_collector.get_recent(1)[0]
    print(f"--- {label}: {prompt}")
    print_request(metric, response=response.choices[0].message.content)
    print()
    explain(metric)
    print()
    if label == "Math problem":
        math_metrics = metric

# --- Routing OFF vs ON -----------------------------------------------
# Without routing you must hard-pick one model and use it for everything —
# the math problem above gets o1-mini only because routing was enabled.
off_config = TokenOptConfig(
    enable_routing=False,
    cache_enabled=False,
    enable_compression=False,
    enable_summarization=False,
    default_model="gpt-4o-mini",
)
off_client = OpenAI(config=off_config)

off_client.chat.completions.create(
    model="gpt-4o-mini",  # the single manual choice
    messages=[{"role": "user", "content": prompts[2][1]}],
)

print_comparison(
    "Routing OFF vs ON (math prompt):",
    off_client.metrics_collector.get_recent(1)[0],
    math_metrics,
)
print()

print_summary(client.get_metrics_summary())
