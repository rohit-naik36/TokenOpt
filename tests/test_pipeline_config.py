"""Pipeline-level enable/disable gating tests for M2 stages."""

from tokenopt.config import TokenOptConfig, get_default_config
from tokenopt.pipeline.base import OptimizationPipeline
from tokenopt.pipeline.compressor import CompressorStage, ContextSummarizerStage
from tokenopt.pipeline.router import RouterStage


def _pipeline(config, *names):
    stages = {
        "router": RouterStage(config),
        "compressor": CompressorStage(config),
        "summarizer": ContextSummarizerStage(config),
    }
    return OptimizationPipeline([stages[n] for n in names], config)


def _messages():
    return [
        {"role": "user", "content": "please explain this in detail"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "what is the weather"},
    ]


def test_defaults_enable_all_stages():
    config = TokenOptConfig()
    ctx = _pipeline(config, "router", "compressor", "summarizer").run(_messages(), "gpt-4o")
    assert "router_latency_ms" in ctx.metrics
    assert "compressor_latency_ms" in ctx.metrics
    assert "summarizer_latency_ms" in ctx.metrics


def test_disabled_stages_are_skipped():
    config = TokenOptConfig(
        enable_routing=False,
        enable_compression=False,
        enable_summarization=False,
    )
    messages = _messages()
    ctx = _pipeline(config, "router", "compressor", "summarizer").run(messages, "gpt-4o")
    assert "router_latency_ms" not in ctx.metrics
    assert "compressor_latency_ms" not in ctx.metrics
    assert "summarizer_latency_ms" not in ctx.metrics
    assert ctx.messages == messages
    assert ctx.model == "gpt-4o"


def test_stage_switches_are_independent():
    config = TokenOptConfig(enable_routing=False)
    ctx = _pipeline(config, "router", "compressor").run(_messages(), "gpt-4o")
    assert "router_latency_ms" not in ctx.metrics
    assert "compressor_latency_ms" in ctx.metrics

    config2 = TokenOptConfig(enable_compression=False)
    ctx2 = _pipeline(config2, "router", "compressor").run(_messages(), "gpt-4o")
    assert "router_latency_ms" in ctx2.metrics
    assert "compressor_latency_ms" not in ctx2.metrics


def test_enabled_router_applies_default_rules():
    config = get_default_config()
    ctx = _pipeline(config, "router").run(
        [{"role": "user", "content": "reason step by step about this logic"}],
        "gpt-4o",
    )
    assert ctx.model == "o1-mini"


def test_enabled_compressor_compresses():
    config = TokenOptConfig()
    messages = [{"role": "user", "content": "the quick brown fox " * 40}]
    ctx = _pipeline(config, "compressor").run(messages, "gpt-4o")
    assert ctx.metrics["compression_applied"] is True
