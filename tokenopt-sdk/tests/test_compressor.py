"""Behavioral contract tests for the compressor stage."""

import sys
import types

import pytest

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.base import OptimizationContext
from tokenopt.pipeline.compressor import CompressorStage
from tokenopt.utils.token_counter import count_tokens


@pytest.fixture
def heuristic_stage(monkeypatch):
    stage = CompressorStage(TokenOptConfig())
    monkeypatch.setattr(stage, "_get_llmlingua", lambda: None)
    return stage


def _ctx(messages, config=None, model="gpt-4o"):
    return OptimizationContext(messages=messages, model=model, config=config or TokenOptConfig())


def test_name():
    assert CompressorStage().name == "compressor"


def test_compression_applied_metric_always_set(heuristic_stage):
    ctx = _ctx([{"role": "user", "content": "hi"}])
    result = heuristic_stage.process(ctx)
    assert result.metrics["compression_applied"] is True


def test_heuristic_collapses_whitespace(heuristic_stage):
    ctx = _ctx([{"role": "user", "content": "line one\n\n\n\nline two   with  spaces"}])
    result = heuristic_stage.process(ctx)
    assert result.messages[0]["content"] == "line one\n\nline two with spaces"


def test_heuristic_removes_filler_phrases(heuristic_stage):
    ctx = _ctx(
        [{"role": "user", "content": "please kindly explain this I think it is basically simple"}]
    )
    result = heuristic_stage.process(ctx)
    content = result.messages[0]["content"]
    assert "please" not in content
    assert "kindly" not in content
    assert "I think" not in content
    assert "basically" not in content
    assert "explain this" in content


def test_heuristic_truncates_long_messages(heuristic_stage):
    content = "the quick brown fox jumps over the lazy dog " * 30
    config = TokenOptConfig(compression_ratio=0.5)
    ctx = _ctx([{"role": "user", "content": content}], config=config)
    result = heuristic_stage.process(ctx)
    target = int(ctx.original_token_count * 0.5)
    assert count_tokens(result.messages[0]["content"]) <= target
    assert count_tokens(result.messages[0]["content"]) < count_tokens(content)


def test_heuristic_preserves_message_structure(heuristic_stage):
    messages = [
        {"role": "system", "content": "You are a helpful assistant. please be concise"},
        {"role": "user", "content": "explain things kindly", "name": "alice"},
    ]
    result = heuristic_stage.process(_ctx(messages))
    assert [m["role"] for m in result.messages] == ["system", "user"]
    assert result.messages[1]["name"] == "alice"
    assert "please" not in result.messages[0]["content"]


def test_heuristic_passes_through_non_string_content(heuristic_stage):
    image_part = {"type": "image_url", "image_url": {"url": "http://example.com/a.png"}}
    messages = [{"role": "user", "content": [image_part]}]
    result = heuristic_stage.process(_ctx(messages))
    assert result.messages[0]["content"] == [image_part]


def test_empty_messages_no_crash(heuristic_stage):
    result = heuristic_stage.process(_ctx([]))
    assert result.messages == []
    assert result.metrics["compression_applied"] is True


def test_tiny_prompt_unchanged(heuristic_stage):
    result = heuristic_stage.process(_ctx([{"role": "user", "content": "hi"}]))
    assert result.messages[0]["content"] == "hi"


def test_message_without_content_key_no_crash(heuristic_stage):
    result = heuristic_stage.process(_ctx([{"role": "user"}]))
    assert result.messages[0] == {"role": "user", "content": ""}


def test_filler_only_message_becomes_empty(heuristic_stage):
    result = heuristic_stage.process(_ctx([{"role": "user", "content": "please kindly"}]))
    assert result.messages[0]["content"] == ""


class _FakeCompressor:
    def __init__(self):
        self.prompts = []

    def compress_prompt(self, prompt, rate=None, force_tokens=None):
        self.prompts.append((prompt, rate, force_tokens))
        return {"compressed_prompt": "compressed text"}


def test_ml_compression_used_when_available():
    stage = CompressorStage(TokenOptConfig())
    fake = _FakeCompressor()
    stage._llmlingua = fake
    ctx = _ctx(
        [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "hello " * 100},
        ]
    )
    result = stage.process(ctx)
    assert result.messages == [{"role": "user", "content": "compressed text"}]
    assert result.metrics["compression_applied"] is True
    prompt, rate, force_tokens = fake.prompts[0]
    assert rate == 0.5
    assert "user: hello" in prompt
    assert force_tokens == [".", "!", "?", "\n"]


def test_ml_failure_falls_back_to_heuristic():
    class _BrokenCompressor:
        def compress_prompt(self, **kwargs):
            raise RuntimeError("llmlingua exploded")

    stage = CompressorStage(TokenOptConfig())
    stage._llmlingua = _BrokenCompressor()
    ctx = _ctx([{"role": "user", "content": "please explain this basically"}])
    result = stage.process(ctx)
    assert result.messages[0]["role"] == "user"
    assert "please" not in result.messages[0]["content"]


def test_get_llmlingua_returns_none_when_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "llmlingua", None)
    stage = CompressorStage(TokenOptConfig())
    assert stage._get_llmlingua() is None


def test_get_llmlingua_loads_and_caches(monkeypatch):
    stub = types.ModuleType("llmlingua")

    class PromptCompressor:
        pass

    stub.PromptCompressor = PromptCompressor
    monkeypatch.setitem(sys.modules, "llmlingua", stub)
    stage = CompressorStage(TokenOptConfig())
    loaded = stage._get_llmlingua()
    assert isinstance(loaded, PromptCompressor)
    assert stage._get_llmlingua() is loaded


def test_deterministic_for_identical_inputs(heuristic_stage):
    messages = [{"role": "user", "content": "please explain this in detail with lots of words"}]
    first = heuristic_stage.process(_ctx(messages))
    second = heuristic_stage.process(_ctx(messages))
    assert first.messages == second.messages


def test_does_not_mutate_original_messages(heuristic_stage):
    messages = [{"role": "user", "content": "please explain this in detail"}]
    expected = [m.copy() for m in messages]
    ctx = _ctx(messages)
    heuristic_stage.process(ctx)
    assert ctx.original_messages == expected
    assert messages == expected
    assert ctx.messages is not messages
