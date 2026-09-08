"""Adaptive Compressor Stage Integration."""

from __future__ import annotations

from typing import Any

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.base import OptimizationContext, PipelineStage

from .adapters import BaseExecutor, PassThroughEvaluator
from .analyzer import Analyzer
from .decider import Decider
from .loop import AdaptiveCompressionLoop


class AdaptiveCompressorStage(PipelineStage):
    """Compress prompts adaptively using segments, bounds, and fidelity."""

    name = "adaptive_compressor"

    def __init__(self, config: TokenOptConfig | None = None):
        self.config = config or TokenOptConfig()
        self._llmlingua: Any = None
        self.analyzer = Analyzer()
        self.decider = Decider()
        self.evaluator = PassThroughEvaluator()

    def _get_llmlingua(self) -> Any:
        if self._llmlingua is None:
            try:
                from llmlingua import PromptCompressor
                self._llmlingua = PromptCompressor()
            except ImportError:
                pass
        return self._llmlingua

    def process(self, ctx: OptimizationContext) -> OptimizationContext:
        executor = BaseExecutor(model=ctx.model, llmlingua_engine=self._get_llmlingua())
        loop = AdaptiveCompressionLoop(executor, self.evaluator, model=ctx.model)

        compressed_messages = []
        total_saved = 0
        total_iterations = 0
        segments_analyzed = 0
        segments_skipped = 0
        segments_fallback = 0

        if not ctx.messages:
            ctx.metrics["compression_applied"] = True
            return ctx

        for i, msg in enumerate(ctx.messages):
            content = msg.get("content", "")
            if not isinstance(content, str):
                compressed_messages.append(msg)
                continue

            segments_analyzed += 1

            role = msg.get("role", "user")
            is_last_user_query = (role == "user" and i == len(ctx.messages) - 1)

            profile = self.analyzer.analyze(
                content,
                role=role,
                segment_id=str(i),
                is_last_user_query=is_last_user_query,
                model=ctx.model
            )
            decision = self.decider.decide(profile)

            if decision.target_technique == "skip" or decision.aggressiveness_ratio == 0.0:
                segments_skipped += 1

            result = loop.optimize_segment(content, decision)

            # Check if fallback occurred (fidelity/latency failed)
            if (
                result.final_fidelity is None
                and decision.target_technique != "skip"
                and decision.target_technique != "whitespace_only"
            ):
                segments_fallback += 1

            total_saved += result.tokens_saved
            total_iterations += result.iterations

            compressed_messages.append({**msg, "content": result.optimized_text})

        ctx.messages = compressed_messages
        ctx.metrics["compression_applied"] = True
        ctx.metrics["compression_tokens_saved"] = total_saved
        ctx.metrics["compression_iterations"] = total_iterations
        ctx.metrics["compression_segments_analyzed"] = segments_analyzed
        ctx.metrics["compression_segments_skipped"] = segments_skipped
        ctx.metrics["compression_fallback_rate"] = (
            (segments_fallback / segments_analyzed) if segments_analyzed > 0 else 0.0
        )
        return ctx
