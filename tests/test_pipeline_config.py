"""Pipeline-level enable/disable gating and fail-open tests."""

from tokenopt.config import TokenOptConfig, get_default_config
from tokenopt.pipeline.base import OptimizationContext, OptimizationPipeline, PipelineStage
from tokenopt.pipeline.cache import CacheStage
from tokenopt.pipeline.compressor import CompressorStage, ContextSummarizerStage
from tokenopt.pipeline.fewshot import FewShotSelectorStage
from tokenopt.pipeline.rag_optimizer import RAGOptimizerStage
from tokenopt.pipeline.router import RouterStage


def _pipeline(config, *names):
    stages = {
        "router": RouterStage(config),
        "compressor": CompressorStage(config),
        "summarizer": ContextSummarizerStage(config),
        "cache": CacheStage(config),
        "rag": RAGOptimizerStage(config),
        "fewshot": FewShotSelectorStage(config),
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


def test_cache_disabled_skips_stage():
    config = TokenOptConfig(cache_enabled=False)
    ctx = _pipeline(config, "cache").run(_messages(), "gpt-4o")
    assert "cache_latency_ms" not in ctx.metrics


def test_cache_enabled_runs_stage():
    config = TokenOptConfig()
    ctx = _pipeline(config, "cache").run(_messages(), "gpt-4o")
    assert "cache_latency_ms" in ctx.metrics
    assert ctx.metrics["cache_hit"] is False


def test_rag_and_fewshot_run_by_default():
    config = TokenOptConfig()
    ctx = _pipeline(config, "rag", "fewshot").run(_messages(), "gpt-4o")
    assert "rag_optimizer_latency_ms" in ctx.metrics
    assert "fewshot_latency_ms" in ctx.metrics


class _BoomStage(PipelineStage):
    name = "boom"

    def process(self, ctx: OptimizationContext) -> OptimizationContext:
        raise RuntimeError("stage exploded")


def test_stage_failure_fails_open():
    config = TokenOptConfig()
    pipeline = OptimizationPipeline([_BoomStage(), RouterStage(config)], config)
    ctx = pipeline.run(_messages(), "gpt-4o")
    assert "boom_error" in ctx.metrics
    assert ctx.model != "gpt-4o"
    assert "router_latency_ms" in ctx.metrics


def test_stage_failure_preserves_messages():
    config = TokenOptConfig()
    messages = _messages()
    pipeline = OptimizationPipeline([_BoomStage()], config)
    ctx = pipeline.run(messages, "gpt-4o")
    assert ctx.messages == messages
    assert "boom_error" in ctx.metrics
