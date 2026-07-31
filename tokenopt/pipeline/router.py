"""Model routing stage for cost/quality optimization."""

from __future__ import annotations

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.base import OptimizationContext, PipelineStage
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
        # Get user query (last user message)
        user_query = self._get_user_query(ctx.messages)
        if not user_query:
            ctx.model = self.config.default_model
            return ctx

        # Check custom routing rules first
        for rule in sorted(self.config.routing_rules, key=lambda r: -r.priority):
            try:
                if rule.condition(user_query, ctx.messages):
                    ctx.model = rule.model
                    ctx.metrics["routing_rule"] = rule.name
                    ctx.metrics["routed_model"] = rule.model
                    return ctx
            except Exception:
                continue

        # Fallback to complexity-based routing
        complexity = self._estimate_complexity(user_query)
        ctx.model = self._select_model_by_complexity(complexity)
        ctx.metrics["routing_complexity"] = complexity
        ctx.metrics["routed_model"] = ctx.model

        return ctx

    def _get_user_query(self, messages: list[dict]) -> str:
        """Extract last user message as query."""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    return content
        return ""

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
