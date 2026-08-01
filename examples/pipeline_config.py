"""Routing — the right model for every request, with the reason why.

Demonstrates the routing precedence contract (Decision 24):

- a matching custom rule wins (math -> o1-mini, code -> gpt-4o)
- custom rules that match NOTHING preserve the requested model instead of
  rewriting it (simple question and complex analysis stay on the default
  gpt-4o-mini, reported as "preserved (no rule matched)")
- without custom rules, built-in complexity routing picks a model by
  keyword + length heuristics (low/medium/high)
- routing_reason: every routing decision records WHY that model was used
  (rule name, "complexity-based (low|medium|high)", or
  "preserved (no rule matched)")
- routing OFF vs ON: without TokenOpt you must pick one model for
  everything; with routing on, each query gets an appropriate model
  automatically

Expected outcome:
Math -> o1-mini (rule math_tasks), code -> gpt-4o (rule code_tasks),
simple and complex questions -> gpt-4o-mini (preserved: no rule matched),
then the same complex question WITHOUT custom rules -> gpt-4o by
complexity routing (high) — and finally the math prompt with routing
disabled, staying on the single manually-chosen model.

Run with an OpenAI API key:

    export OPENAI_API_KEY=sk-...          # macOS/Linux
    $env:OPENAI_API_KEY = "sk-..."        # PowerShell
"""

from _format import explain, print_comparison, print_request, print_summary, quiet

from tokenopt import OpenAI, RoutingRule, TokenOptConfig, create_client_from_model


def is_math_query(query: str, messages: list[dict]) -> bool:
    """Routing rule condition: true for math-related questions."""
    return any(token in query.lower() for token in ("math", "equation", "integral", "derivative"))


def is_code_query(query: str, messages: list[dict]) -> bool:
    """Routing rule condition: true for code-related requests."""
    return any(token in query.lower() for token in ("code", "function", "debug", "implement"))


# Custom rules REPLACE the defaults. A matched rule picks its model; an
# unmatched request PRESERVES the caller's model (never rewritten — the
# default_model only applies to requests that are not explicitly routed).
# Priority decides which rule wins when several match.
config = TokenOptConfig(
    enable_routing=True,
    routing_rules=[
        RoutingRule(
            name="math_tasks",
            condition=is_math_query,
            model="o1-mini",          # strong reasoning model
            priority=40,
        ),
        RoutingRule(
            name="code_tasks",
            condition=is_code_query,
            model="gpt-4o",           # solid code model
            priority=30,
        ),
    ],
    default_model="gpt-4o-mini",      # cheap default when nothing matches
    cache_enabled=False,
)

client = create_client_from_model("gpt-4o", api_key=None, config=config)
quiet()

prompts = [
    ("Math problem", "Solve the equation x^2 = 49 for x."),
    ("Code request", "Write a python function that implements binary search."),
    ("Simple question", "What is the capital of France?"),
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

# --- Complexity routing (no custom rules) -------------------------------
# Precedence 4: with no routing_rules at all, the built-in complexity
# heuristic decides (keyword + length -> low/medium/high).
complexity_client = OpenAI(config=TokenOptConfig(cache_enabled=False))
complexity_client.chat.completions.create(
    messages=[{"role": "user", "content": prompts[3][1]}],
)
print(f"--- No custom rules: {prompts[3][0].lower()} (complexity routing decides)")
explain(complexity_client.metrics_collector.get_recent(1)[0])
print()

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
    messages=[{"role": "user", "content": prompts[0][1]}],
)

print_comparison(
    "Routing OFF vs ON (math prompt):",
    off_client.metrics_collector.get_recent(1)[0],
    math_metrics,
)
print()

print_summary(client.get_metrics_summary())
