"""Usage, census-weighted cost and dollar cost for Stage 2 (Claude API). Stdlib only.

Census weights follow tokenopt census (experiments/sdlc_census/census.py on feat/workflow-optimizer):
W = uncached * 1 + cached * 0.1 + output * 4. The census has no cache-write term, so cache-creation
tokens are weighted 1 (same as uncached input). That understates cache-write cost in W; the dollar
figure is the one that prices cache writes, once the prices file has them.

A census "turn" is one provider call, which is one JSONL row here; nothing about the turn is redefined.
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
PRICES_PATH = HERE / "stage2_prices.json"
W_CACHE_READ, W_OUTPUT = 0.1, 4.0
USAGE_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def load_prices(path=PRICES_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def zero_usage():
    return {k: 0 for k in USAGE_KEYS}


def as_usage(raw):
    """Normalise a provider usage object; missing cache fields count as 0 (API omits them when caching is off)."""
    return {k: int((raw or {}).get(k) or 0) for k in USAGE_KEYS}


def weighted(usage):
    return (usage["input_tokens"] + usage["cache_creation_input_tokens"]) * 1.0 \
        + usage["cache_read_input_tokens"] * W_CACHE_READ + usage["output_tokens"] * W_OUTPUT


def _price(prices, model, unit):
    v = prices.get(model, {}).get(unit)
    return v if isinstance(v, (int, float)) else None


def unpriced_units(prices, model, usage):
    """Units with a non-zero count but no numeric price yet (TODO). Empty list = dollar cost is computable."""
    need = {
        "input": usage["input_tokens"],
        "output": usage["output_tokens"],
        "cache_write_5m": usage["cache_creation_input_tokens"],
        "cache_read": usage["cache_read_input_tokens"],
    }
    return [u for u, n in need.items() if n and _price(prices, model, u) is None]


def dollars(usage, prices, model):
    """USD for one call, or None if any non-zero unit is unpriced. Prices are USD per 1M tokens."""
    if unpriced_units(prices, model, usage):
        return None
    total = 0.0
    for unit, key in (("input", "input_tokens"), ("output", "output_tokens"),
                      ("cache_write_5m", "cache_creation_input_tokens"), ("cache_read", "cache_read_input_tokens")):
        if usage[key]:
            total += usage[key] * _price(prices, model, unit) / 1_000_000
    return total


def census_turns(rows):
    """Adapter: one (prompt, cached, completion) tuple per call row, the shape census.py reads from provider usage.

    prompt counts every input token (uncached + cache write + cache read), cached is the cache-read part.
    """
    out = []
    for r in rows:
        u = r["usage"]
        prompt = u["input_tokens"] + u["cache_creation_input_tokens"] + u["cache_read_input_tokens"]
        out.append((prompt, u["cache_read_input_tokens"], u["output_tokens"]))
    return out
