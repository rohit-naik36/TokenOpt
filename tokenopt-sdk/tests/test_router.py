"""Behavioral contract tests for the router stage."""

from tokenopt.config import RoutingRule, TokenOptConfig, get_default_config
from tokenopt.pipeline.base import OptimizationContext
from tokenopt.pipeline.router import RouterStage


def _ctx(query, config, messages=None, model="gpt-4o-mini", model_explicit=False):
    if messages is None:
        messages = [{"role": "user", "content": query}]
    return OptimizationContext(
        messages=messages,
        model=model,
        config=config,
        model_explicit=model_explicit,
    )


def _route(query, config, **ctx_kwargs):
    return RouterStage(config).process(_ctx(query, config, **ctx_kwargs))


def test_name():
    assert RouterStage().name == "router"


def test_empty_messages_preserve_resolved_model():
    config = TokenOptConfig(default_model="custom-model")
    ctx = _ctx("", config, messages=[{"role": "system", "content": "be brief"}])
    result = RouterStage(config).process(ctx)
    assert result.model == "gpt-4o-mini"
    assert result.metrics["routing_precedence"] == "provider_default"


def test_empty_query_preserves_resolved_model():
    config = TokenOptConfig(default_model="custom-model")
    result = _route("", config)
    assert result.model == "gpt-4o-mini"
    assert result.metrics["routing_precedence"] == "provider_default"


def test_non_string_user_content_preserves_resolved_model():
    config = TokenOptConfig(default_model="custom-model")
    ctx = _ctx("", config, messages=[{"role": "user", "content": [{"type": "text", "text": "hi"}]}])
    result = RouterStage(config).process(ctx)
    assert result.model == "gpt-4o-mini"


def test_last_user_message_is_used_for_routing():
    config = get_default_config()
    messages = [
        {"role": "user", "content": "analyze and compare the architecture"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "what is the weather"},
    ]
    result = RouterStage(config).process(_ctx("", config, messages=messages))
    assert result.model == "gpt-4o-mini"
    assert result.metrics["routing_rule"] == "simple_queries"


def test_default_rules_priority_simple():
    config = get_default_config()
    result = _route("what is the weather today", config)
    assert result.model == "gpt-4o-mini"
    assert result.metrics["routing_rule"] == "simple_queries"


def test_default_rules_priority_code_over_simple():
    config = get_default_config()
    result = _route("write code to sort a list", config)
    assert result.model == "gpt-4o"
    assert result.metrics["routing_rule"] == "code_tasks"


def test_default_rules_priority_reasoning_over_code():
    config = get_default_config()
    result = _route("reason step by step about this code", config)
    assert result.model == "o1-mini"
    assert result.metrics["routing_rule"] == "reasoning_tasks"


def test_custom_rule_wins_by_highest_priority():
    config = TokenOptConfig(
        routing_rules=[
            RoutingRule(name="low_prio", condition=lambda q, m: True, model="gpt-4o", priority=1),
            RoutingRule(
                name="high_prio",
                condition=lambda q, m: True,
                model="claude-3-5-sonnet",
                priority=99,
            ),
        ]
    )
    result = _route("anything", config)
    assert result.model == "claude-3-5-sonnet"
    assert result.metrics["routing_rule"] == "high_prio"


def test_first_matching_rule_stops_evaluation():
    def never_called(query, messages):
        raise AssertionError("lower-priority rule must not be evaluated")

    config = TokenOptConfig(
        routing_rules=[
            RoutingRule(name="match_all", condition=lambda q, m: True, model="gpt-4o", priority=50),
            RoutingRule(
                name="never_checked",
                condition=never_called,
                model="gpt-4o-mini",
                priority=10,
            ),
        ]
    )
    result = _route("anything", config)
    assert result.model == "gpt-4o"
    assert "never_checked" not in result.metrics


def test_rule_exception_is_skipped_fail_open():
    def boom(query, messages):
        raise RuntimeError("broken rule")

    config = TokenOptConfig(
        routing_rules=[
            RoutingRule(name="broken", condition=boom, model="gpt-4o", priority=50),
            RoutingRule(
                name="fallback_rule",
                condition=lambda q, m: True,
                model="gpt-4o-mini",
                priority=10,
            ),
        ]
    )
    result = _route("anything", config)
    assert result.model == "gpt-4o-mini"
    assert result.metrics["routing_rule"] == "fallback_rule"


def test_all_rules_failing_preserves_caller_model():
    def boom(query, messages):
        raise RuntimeError("broken rule")

    config = TokenOptConfig(
        routing_rules=[RoutingRule(name="broken", condition=boom, model="gpt-4o", priority=50)]
    )
    result = _route("analyze this", config)
    assert result.model == "gpt-4o-mini"
    assert result.metrics["routing_precedence"] == "preserve"
    assert "routing_complexity" not in result.metrics


def test_explicit_model_wins_over_matching_rule():
    config = TokenOptConfig(
        routing_rules=[
            RoutingRule(name="catch_all", condition=lambda q, m: True, model="gpt-4o", priority=50)
        ]
    )
    result = _route("anything", config, model="gpt-4o-mini", model_explicit=True)
    assert result.model == "gpt-4o-mini"
    assert result.metrics["routing_precedence"] == "explicit"
    assert "routing_rule" not in result.metrics


def test_explicit_model_wins_over_complexity():
    result = _route("analyze this", TokenOptConfig(), model="gpt-4o", model_explicit=True)
    assert result.model == "gpt-4o"
    assert result.metrics["routing_precedence"] == "explicit"


def test_explicit_model_wins_without_query():
    config = TokenOptConfig(default_model="custom-model")
    result = _route("", config, model="gpt-4o-mini", model_explicit=True)
    assert result.model == "gpt-4o-mini"
    assert result.metrics["routing_precedence"] == "explicit"


def test_custom_rules_no_match_preserves_caller_model():
    config = TokenOptConfig(
        routing_rules=[
            RoutingRule(
                name="math_tasks",
                condition=lambda q, m: "equation" in q.lower(),
                model="o1-mini",
                priority=40,
            )
        ]
    )
    result = _route("what is the weather", config)
    assert result.model == "gpt-4o-mini"
    assert result.metrics["routing_precedence"] == "preserve"


def test_builtin_rules_no_match_uses_complexity_fallback():
    """Default-config rules alone still fall back to complexity routing."""
    config = get_default_config()
    result = _route("analyze and compare the architecture", config)
    assert result.model == "gpt-4o"
    assert result.metrics["routing_complexity"] == "high"
    assert result.metrics["routing_precedence"] == "complexity"


def test_mixed_custom_and_builtin_rules_no_match_preserves():
    """A custom rule anywhere in the config moves unmatched requests to preserve."""
    config = get_default_config()
    config.routing_rules = config.routing_rules + [
        RoutingRule(
            name="derivatives",
            condition=lambda q, m: "derivative" in q.lower(),
            model="o1-mini",
            priority=40,
        )
    ]
    result = _route("analyze and compare the architecture", config)
    assert result.model == "gpt-4o-mini"
    assert result.metrics["routing_precedence"] == "preserve"


def test_complexity_fallback_high_keywords():
    result = _route("analyze and compare the detailed architecture", TokenOptConfig())
    assert result.model == "gpt-4o"
    assert result.metrics["routing_complexity"] == "high"


def test_complexity_fallback_medium_keywords():
    result = _route("explain how to implement a function", TokenOptConfig())
    assert result.model == "gpt-4o"
    assert result.metrics["routing_complexity"] == "medium"


def test_complexity_fallback_low_keywords():
    result = _route("what is the weather", TokenOptConfig())
    assert result.model == "gpt-4o-mini"
    assert result.metrics["routing_complexity"] == "low"


def test_complexity_token_threshold_medium():
    query = "hello world " * 150
    result = _route(query, TokenOptConfig())
    assert result.metrics["routing_complexity"] == "medium"
    assert result.model == "gpt-4o"


def test_complexity_token_threshold_high():
    query = "hello world " * 600
    result = _route(query, TokenOptConfig())
    assert result.metrics["routing_complexity"] == "high"
    assert result.model == "gpt-4o"


def test_deterministic_for_identical_inputs():
    config = TokenOptConfig()
    stage = RouterStage(config)
    first = stage.process(_ctx("explain this code to me", config))
    second = stage.process(_ctx("explain this code to me", config))
    assert first.model == second.model
    assert first.metrics == second.metrics


def test_does_not_mutate_messages():
    config = get_default_config()
    messages = [{"role": "user", "content": "analyze this architecture"}]
    expected = [m.copy() for m in messages]
    ctx = OptimizationContext(messages=messages, model="gpt-4o-mini", config=config)
    RouterStage(config).process(ctx)
    assert ctx.messages == expected
    assert ctx.original_messages == expected
