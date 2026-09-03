"""Observability — every metric explained, and why the overhead is minimal.

Demonstrates:
- the full per-request metrics breakdown, field by field
- the latency split: total = model inference + TokenOpt pipeline overhead,
  and how a cache hit collapses the overhead
- per-request metrics delivered to your own monitoring via a callback
- aggregated summary and standalone token/cost utilities

Expected outcome:
Two identical requests: a cache miss (full pipeline + model call) and a cache
hit (overhead only, ~1 ms). Each printed metric is annotated so you know
exactly what it measures — and where your money and time actually go.

Run with an OpenAI API key:

    export OPENAI_API_KEY=sk-...          # macOS/Linux
    $env:OPENAI_API_KEY = "sk-..."        # PowerShell
"""

from _format import explain, print_request, print_summary, quiet

from tokenopt import OpenAI, RequestMetrics, TokenOptConfig, count_message_tokens, estimate_cost


def on_request(metrics: RequestMetrics) -> None:
    """Example callback: called once per request with its metrics.

    Wire this to your own monitoring (statsd, Prometheus, log aggregators).
    The callback can never break requests — exceptions are swallowed.
    """
    print(
        f"  [callback] model={metrics.model} "
        f"tokens={metrics.original_tokens}->{metrics.optimized_tokens} "
        f"(saved {metrics.tokens_saved:+d}) "
        f"routed={metrics.routing_applied} cache_hit={metrics.cache_hit}"
    )


config = TokenOptConfig(metrics_callback=on_request)
client = OpenAI(config=config)
quiet()

messages = [
    {"role": "user", "content": (
        "Could you please explain what the TokenOpt overhead metric means, "
        "I think it measures the time the optimization pipeline itself takes, "
        "basically the stages running before the model call."
    )},
]

print("Request 1 (cache miss — full pipeline + model call):")
response = client.chat.completions.create(model="gpt-4o", messages=messages)
print()
metric = client.metrics_collector.get_recent(1)[0]
print_request(metric, response=response.choices[0].message.content)

# Field-by-field annotation, derived from the recorded metrics themselves.
print()
print("What each field measures:")
print(f"  original_tokens={metric.original_tokens} - prompt tokens BEFORE any optimization")
print(f"  optimized_tokens={metric.optimized_tokens} - what the model actually received")
print(f"  tokens_saved={metric.tokens_saved} / "
      f"reduction_percentage={metric.reduction_percentage:.1f}% - the compression win")
print(f"  compression_attempted={metric.compression_attempted} - the compressor stage ran")
print(f"  compression_effective={metric.compression_effective} - tokens were actually reduced")
print(f"  routing_reason='{metric.routing_reason}' - why this model was chosen")
print(f"  model_latency_ms={metric.model_latency_ms:.1f} - time the model inference took")
print(f"  pipeline_latency_ms={metric.pipeline_latency_ms:.1f} - TokenOpt's own overhead")
print(f"  latency_ms={metric.latency_ms:.1f} - total, i.e. model + overhead")
print(f"  estimated_cost=${metric.estimated_cost:.6f} - approximate USD for this request")
print()
explain(metric)
print()

print("Request 2 (identical — cache hit, no model call):")
client.chat.completions.create(model="gpt-4o", messages=messages)
print()
hit = client.metrics_collector.get_recent(1)[0]
print_request(hit, response=response.choices[0].message.content)

# The overhead story: the pipeline stages always run (~ms), but on a cache
# hit there is no model call at all, so the total collapses to overhead only.
print()
explain(hit)
print()

print_summary(client.get_metrics_summary())
print()

# Standalone utilities
utility_messages = [{"role": "user", "content": "Count my tokens"}]
print("Message tokens:", count_message_tokens(utility_messages, "gpt-4o"))
print("Estimated cost (gpt-4o, 100 in / 50 out):", estimate_cost("gpt-4o", 100, 50), "USD")
