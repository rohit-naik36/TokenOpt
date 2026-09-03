"""Model routing stage for cost/quality optimization.

Routing precedence contract (Decision 24, principle of least surprise):

1. **Explicit caller model** — a model passed to the client is never
   overridden (``ctx.model_explicit``).
2. **Matching routing rule** — rules (custom and built-in) are evaluated
   in priority order; the first match wins.
3. **Custom rules exist but none match** — the caller's requested model
   is preserved (a no-match never rewrites the model; fail-open friendly).
4. **No custom routing configuration** — built-in complexity routing
   (keyword + token-count heuristic) applies.
5. **Provider default (last resort)** — nothing routes; the resolved
   model stands.

Every decision records ``routing_precedence``
(``explicit | rule | preserve | complexity | provider_default``) in
``ctx.metrics``; matches also record ``routing_rule`` + ``routed_model``,
and complexity routing records ``routing_complexity``.
"""

from __future__ import annotations

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.base import OptimizationContext, PipelineStage
from tokenopt.utils.messages import get_user_query
from tokenopt.utils.token_counter import count_message_tokens


class RouterStage(PipelineStage):
    """Route requests to optimal model based on query characteristics."""

    name = "router"

    def __init__(self, config: TokenOptConfig | None = None):
        self.config = config or TokenOptConfig()
        self._complexity_keywords = {
            "high": ["analyze", "compare", "detailed", "comprehensive", "reason", "step by step",
                     "think", "logic", "proof", "derive", "complex", "architecture", "design"],
            "medium": ["explain", "describe", "summarize", "list", "example", "implement",
                       "code", "function", "debug", "refactor", "write", "create"],
            "low": ["what", "who", "when", "where", "define", "translate", "convert", "format"],
        }

    def process(self, ctx: OptimizationContext) -> OptimizationContext:
        # Precedence 1: an explicit caller model is never overridden.
        if ctx.model_explicit:
            ctx.metrics["routing_precedence"] = "explicit"
            return ctx

        # Precedence 5: without a query there is nothing to route on; the
        # resolved (caller or default) model stands.
        user_query = get_user_query(ctx.messages)
        if not user_query:
            ctx.metrics["routing_precedence"] = "provider_default"
            return ctx

        # Precedence 2: first matching rule (custom or built-in) wins.
        for rule in sorted(self.config.routing_rules, key=lambda r: -r.priority):
            try:
                if rule.condition(user_query, ctx.messages):
                    ctx.model = rule.model
                    ctx.metrics["routing_rule"] = rule.name
                    ctx.metrics["routed_model"] = rule.model
                    ctx.metrics["routing_precedence"] = "rule"
                    return ctx
            except Exception:
                continue

        # Precedence 3: custom rules exist but none matched — preserve the
        # caller's requested model instead of rewriting it.
        if self._has_custom_rules():
            ctx.metrics["routing_precedence"] = "preserve"
            return ctx

        # Precedence 4: no custom routing configuration — built-in
        # complexity routing.
        complexity = self._estimate_complexity(user_query)
        ctx.model = self._select_model_by_complexity(complexity)
        ctx.metrics["routing_complexity"] = complexity
        ctx.metrics["routed_model"] = ctx.model
        ctx.metrics["routing_precedence"] = "complexity"

        return ctx

    def _has_custom_rules(self) -> bool:
        """True when any user-supplied (non-builtin) rule is configured."""
        return any(not rule.builtin for rule in self.config.routing_rules)

    def _estimate_complexity(self, query: str) -> str:
        """Estimate query complexity from keywords."""
        query_lower = query.lower()

        high_score = sum(1 for k in self._complexity_keywords["high"] if k in query_lower)
        medium_score = sum(1 for k in self._complexity_keywords["medium"] if k in query_lower)

        # Weight by token count
        token_count = count_message_tokens([{"role": "user", "content": query}], "gpt-4o")

        if high_score > 0 or token_count > 1000:
            return "high"
        elif medium_score > 0 or token_count > 200:
            return "medium"
        return "low"

    def _select_model_by_complexity(self, complexity: str) -> str:
        """Select model based on complexity tier."""
        model_map = {
            "high": "gpt-4o",      # Best quality for complex tasks
            "medium": "gpt-4o",    # Balanced
            "low": "gpt-4o-mini",  # Fast/cheap for simple tasks
        }
        return model_map.get(complexity, self.config.default_model)
