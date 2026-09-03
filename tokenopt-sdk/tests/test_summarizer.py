"""Behavioral contract tests for the context summarizer stage."""

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.base import OptimizationContext
from tokenopt.pipeline.compressor import ContextSummarizerStage


def _ctx(messages, config=None, model="gpt-4o"):
    return OptimizationContext(messages=messages, model=model, config=config or TokenOptConfig())


def _six_messages():
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "first query"},
        {"role": "assistant", "content": "first answer"},
        {"role": "user", "content": "second query"},
        {"role": "assistant", "content": "second answer"},
        {"role": "user", "content": "third query"},
    ]


def test_name():
    assert ContextSummarizerStage().name == "summarizer"


def test_two_or_fewer_messages_never_summarized():
    config = TokenOptConfig(summarization_threshold=1)
    messages = [
        {"role": "user", "content": "x" * 3000},
        {"role": "assistant", "content": "y" * 3000},
    ]
    ctx = _ctx(messages, config)
    result = ContextSummarizerStage(config).process(ctx)
    assert result.messages == messages
    assert "summarization_applied" not in result.metrics


def test_below_threshold_is_no_op():
    config = TokenOptConfig(summarization_threshold=100000)
    messages = _six_messages()
    ctx = _ctx(messages, config)
    result = ContextSummarizerStage(config).process(ctx)
    assert result.messages == messages
    assert "summarization_applied" not in result.metrics


def test_three_or_fewer_non_system_messages_are_no_op():
    config = TokenOptConfig(summarization_threshold=10)
    messages = [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "two"},
        {"role": "user", "content": "three"},
    ]
    ctx = _ctx(messages, config)
    result = ContextSummarizerStage(config).process(ctx)
    assert result.messages == messages
    assert "summarization_applied" not in result.metrics


def test_summarizes_history_and_keeps_recent_context():
    config = TokenOptConfig(summarization_threshold=10)
    ctx = _ctx(_six_messages(), config)
    result = ContextSummarizerStage(config).process(ctx)
    assert result.messages[0] == {"role": "system", "content": "You are a helpful assistant."}
    assert result.messages[1]["role"] == "system"
    assert "Previous conversation summary:" in result.messages[1]["content"]
    assert result.messages[2:] == [
        {"role": "user", "content": "second query"},
        {"role": "assistant", "content": "second answer"},
        {"role": "user", "content": "third query"},
    ]
    assert result.metrics["summarization_applied"] is True
    assert result.metrics["summarized_messages"] == 2


def test_summarization_without_system_message():
    config = TokenOptConfig(summarization_threshold=10)
    messages = [
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "two"},
        {"role": "user", "content": "three"},
        {"role": "assistant", "content": "four"},
        {"role": "user", "content": "five"},
    ]
    result = ContextSummarizerStage(config).process(_ctx(messages, config))
    assert result.messages[0]["role"] == "system"
    assert "Previous conversation summary:" in result.messages[0]["content"]
    assert result.messages[1:] == [
        {"role": "user", "content": "three"},
        {"role": "assistant", "content": "four"},
        {"role": "user", "content": "five"},
    ]


def test_custom_summarizer_fn_used():
    config = TokenOptConfig(summarization_threshold=10)
    calls = []

    def custom_fn(messages, model):
        calls.append(([m.copy() for m in messages], model))
        return "CUSTOM SUMMARY"

    stage = ContextSummarizerStage(config, summarizer_fn=custom_fn)
    result = stage.process(_ctx(_six_messages(), config))
    assert "CUSTOM SUMMARY" in result.messages[1]["content"]
    assert len(calls) == 1
    history, model = calls[0]
    assert model == "gpt-4o"
    assert [m["role"] for m in history] == ["user", "assistant"]


def test_extractive_fallback_first_and_last_user_messages():
    config = TokenOptConfig(summarization_threshold=10)
    messages = [
        {"role": "user", "content": "first question alpha"},
        {"role": "assistant", "content": "answer a1"},
        {"role": "user", "content": "second question beta"},
        {"role": "assistant", "content": "answer a2"},
        {"role": "user", "content": "third question gamma"},
        {"role": "assistant", "content": "answer a3"},
    ]
    result = ContextSummarizerStage(config).process(_ctx(messages, config))
    summary = result.messages[0]["content"]
    assert "First query: first question alpha" in summary
    assert "Last query: second question beta" in summary


def test_extractive_fallback_no_user_messages():
    config = TokenOptConfig(summarization_threshold=10)
    messages = [
        {"role": "assistant", "content": "a1"},
        {"role": "assistant", "content": "a2"},
        {"role": "assistant", "content": "a3"},
        {"role": "assistant", "content": "a4"},
    ]
    result = ContextSummarizerStage(config).process(_ctx(messages, config))
    assert "No user messages to summarize." in result.messages[0]["content"]


def test_extractive_fallback_truncates_long_queries():
    config = TokenOptConfig(summarization_threshold=10)
    long_query = "q" * 500
    messages = [
        {"role": "user", "content": long_query},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "next"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "last"},
    ]
    result = ContextSummarizerStage(config).process(_ctx(messages, config))
    summary = result.messages[0]["content"]
    assert "q" * 200 in summary
    assert "q" * 201 not in summary


def test_malformed_content_does_not_crash():
    config = TokenOptConfig(summarization_threshold=10)
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "q3"},
    ]
    result = ContextSummarizerStage(config).process(_ctx(messages, config))
    assert "No user messages to summarize." in result.messages[0]["content"]


def test_deterministic_for_identical_inputs():
    config = TokenOptConfig(summarization_threshold=10)
    stage = ContextSummarizerStage(config)
    first = stage.process(_ctx(_six_messages(), config))
    second = stage.process(_ctx(_six_messages(), config))
    assert first.messages == second.messages
    assert first.metrics == second.metrics


def test_does_not_mutate_original_messages():
    config = TokenOptConfig(summarization_threshold=10)
    messages = _six_messages()
    expected = [m.copy() for m in messages]
    ctx = _ctx(messages, config)
    ContextSummarizerStage(config).process(ctx)
    assert ctx.original_messages == expected
    assert messages == expected
