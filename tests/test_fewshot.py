"""Behavioral contract tests for the few-shot selector stage."""

import random

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.base import OptimizationContext
from tokenopt.pipeline.fewshot import FewShotSelectorStage

EXAMPLES = [
    {"input": "input one", "output": "output one"},
    {"input": "input two", "output": "output two"},
    {"input": "input three", "output": "output three"},
]

EX_TEXT_1 = "Input: input one\nOutput: output one"
EX_TEXT_2 = "Input: input two\nOutput: output two"
EX_TEXT_3 = "Input: input three\nOutput: output three"

QUERY = "what is the weather"


class _ScriptedProvider:
    """Embedding provider with scripted similarity for deterministic tests."""

    def __init__(self, sim_table):
        self._table = sim_table

    def embed(self, texts):
        return list(texts)

    def embed_single(self, text):
        return text

    def similarity(self, a, b):
        return self._table.get((a, b), self._table.get((b, a), 0.0))


def _ctx(config, messages=None):
    if messages is None:
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": QUERY},
        ]
    return OptimizationContext(messages=messages, model="gpt-4o", config=config)


def _stage(config, examples=None):
    return FewShotSelectorStage(config, examples=examples or list(EXAMPLES))


def test_name():
    assert FewShotSelectorStage(TokenOptConfig()).name == "fewshot"


def test_no_examples_is_no_op():
    config = TokenOptConfig()
    stage = FewShotSelectorStage(config, examples=[])
    ctx = _ctx(config)
    result = stage.process(ctx)
    assert result.messages == ctx.messages
    assert result.metrics == {}


def test_no_user_query_is_no_op():
    config = TokenOptConfig()
    stage = _stage(config)
    messages = [{"role": "system", "content": "You are a helpful assistant."}]
    ctx = _ctx(config, messages=messages)
    result = stage.process(ctx)
    assert result.messages == messages
    assert result.metrics == {}


def test_similarity_selects_top_examples():
    config = TokenOptConfig(fewshot_selection_strategy="similarity", fewshot_max_examples=2)
    stage = _stage(config)
    stage._embedding_provider = _ScriptedProvider(
        {
            (QUERY, EX_TEXT_1): 0.9,
            (QUERY, EX_TEXT_2): 0.8,
            (QUERY, EX_TEXT_3): 0.7,
        }
    )
    result = stage.process(_ctx(config))
    assert result.metrics["fewshot_selected"] == 2
    assert result.metrics["fewshot_applied"] is True
    roles = [m["role"] for m in result.messages]
    assert roles == ["system", "user", "assistant", "user", "assistant", "user"]
    assert result.messages[1]["content"] == "input one"
    assert result.messages[2]["content"] == "output one"
    assert result.messages[3]["content"] == "input two"
    assert result.messages[4]["content"] == "output two"


def test_similarity_max_examples_cap():
    config = TokenOptConfig(fewshot_selection_strategy="similarity", fewshot_max_examples=1)
    stage = _stage(config)
    stage._embedding_provider = _ScriptedProvider(
        {
            (QUERY, EX_TEXT_1): 0.9,
            (QUERY, EX_TEXT_2): 0.8,
            (QUERY, EX_TEXT_3): 0.7,
        }
    )
    result = stage.process(_ctx(config))
    assert result.metrics["fewshot_selected"] == 1
    assert [m["role"] for m in result.messages] == ["system", "user", "assistant", "user"]


def test_fewer_examples_than_max():
    config = TokenOptConfig(fewshot_selection_strategy="similarity", fewshot_max_examples=5)
    stage = _stage(config)
    stage._embedding_provider = _ScriptedProvider(
        {
            (QUERY, EX_TEXT_1): 0.9,
            (QUERY, EX_TEXT_2): 0.8,
            (QUERY, EX_TEXT_3): 0.7,
        }
    )
    result = stage.process(_ctx(config))
    assert result.metrics["fewshot_selected"] == 3


def test_default_config_uses_similarity_with_cap_three():
    config = TokenOptConfig()
    stage = _stage(config, examples=EXAMPLES)
    stage._embedding_provider = _ScriptedProvider(
        {
            (QUERY, EX_TEXT_1): 0.9,
            (QUERY, EX_TEXT_2): 0.8,
            (QUERY, EX_TEXT_3): 0.7,
        }
    )
    result = stage.process(_ctx(config))
    assert result.metrics["fewshot_selected"] == 3


def test_diversity_selection_is_deterministic():
    config = TokenOptConfig(fewshot_selection_strategy="diversity", fewshot_max_examples=2)
    stage = _stage(config)
    stage._embedding_provider = _ScriptedProvider(
        {
            (QUERY, EX_TEXT_1): 0.9,
            (QUERY, EX_TEXT_2): 0.85,
            (QUERY, EX_TEXT_3): 0.75,
            (EX_TEXT_1, EX_TEXT_2): 0.95,
            (EX_TEXT_1, EX_TEXT_3): 0.1,
            (EX_TEXT_2, EX_TEXT_3): 0.0,
        }
    )
    result = stage.process(_ctx(config))
    assert result.metrics["fewshot_selected"] == 2
    assert result.messages[1]["content"] == "input one"
    assert result.messages[3]["content"] == "input three"


def test_diversity_max_one_selects_first():
    config = TokenOptConfig(fewshot_selection_strategy="diversity", fewshot_max_examples=1)
    stage = _stage(config)
    stage._embedding_provider = _ScriptedProvider({})
    result = stage.process(_ctx(config))
    assert result.metrics["fewshot_selected"] == 1
    assert result.messages[1]["content"] == "input one"


def test_random_strategy_uses_sample(monkeypatch):
    config = TokenOptConfig(fewshot_selection_strategy="random", fewshot_max_examples=2)
    calls = []

    def fake_sample(seq, k):
        calls.append((list(seq), k))
        return list(seq)[:k]

    monkeypatch.setattr(random, "sample", fake_sample)
    stage = _stage(config)
    result = stage.process(_ctx(config))
    assert result.metrics["fewshot_selected"] == 2
    assert result.messages[1]["content"] == "input one"
    assert calls[0][1] == 2


def test_injection_without_system_message_prepends():
    config = TokenOptConfig(fewshot_selection_strategy="similarity", fewshot_max_examples=2)
    stage = _stage(config)
    stage._embedding_provider = _ScriptedProvider(
        {
            (QUERY, EX_TEXT_1): 0.9,
            (QUERY, EX_TEXT_2): 0.8,
            (QUERY, EX_TEXT_3): 0.7,
        }
    )
    messages = [{"role": "user", "content": QUERY}]
    result = stage.process(_ctx(config, messages=messages))
    assert result.metrics["fewshot_applied"] is True
    assert result.messages[0] == {"role": "user", "content": "input one"}
    assert result.messages[2] == {"role": "user", "content": "input two"}
    assert result.messages[-1] == {"role": "user", "content": QUERY}


def test_example_without_output_injects_only_input():
    config = TokenOptConfig(fewshot_selection_strategy="similarity", fewshot_max_examples=2)
    stage = FewShotSelectorStage(
        config,
        examples=[
            {"input": "input one"},
            {"input": "input two", "output": "output two"},
        ],
    )
    stage._embedding_provider = _ScriptedProvider({})
    result = stage.process(_ctx(config))
    assert result.metrics["fewshot_selected"] == 2
    assert result.messages[1]["role"] == "user"
    assert result.messages[2]["role"] == "user"


def test_deterministic_for_identical_inputs():
    config = TokenOptConfig(fewshot_selection_strategy="similarity", fewshot_max_examples=2)
    stage = _stage(config)
    stage._embedding_provider = _ScriptedProvider(
        {
            (QUERY, EX_TEXT_1): 0.9,
            (QUERY, EX_TEXT_2): 0.8,
            (QUERY, EX_TEXT_3): 0.7,
        }
    )
    first = stage.process(_ctx(config))
    second = stage.process(_ctx(config))
    assert first.messages == second.messages
    assert first.metrics == second.metrics


def test_does_not_mutate_original_messages():
    config = TokenOptConfig(fewshot_selection_strategy="similarity", fewshot_max_examples=2)
    stage = _stage(config)
    stage._embedding_provider = _ScriptedProvider(
        {
            (QUERY, EX_TEXT_1): 0.9,
            (QUERY, EX_TEXT_2): 0.8,
            (QUERY, EX_TEXT_3): 0.7,
        }
    )
    ctx = _ctx(config)
    expected = [m.copy() for m in ctx.original_messages]
    stage.process(ctx)
    assert ctx.original_messages == expected
    assert ctx.original_messages[1] == {"role": "user", "content": QUERY}
