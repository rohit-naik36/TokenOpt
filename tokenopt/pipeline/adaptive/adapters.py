"""Adapters bridging existing components to the new Adaptive Architecture."""

from __future__ import annotations

import re
from typing import Any

from tokenopt.pipeline.adaptive.contracts import (
    CompressionDecision,
    Evaluator,
    Executor,
    FidelityResult,
)
from tokenopt.utils.token_counter import count_tokens, truncate_to_tokens


class BaseExecutor(Executor):
    """Executes compression using heuristics or ML semantic reduction."""

    def __init__(self, model: str, llmlingua_engine: Any = None) -> None:
        self.model = model
        self.llmlingua_engine = llmlingua_engine

    def execute(self, text: str, decision: CompressionDecision) -> str:
        if decision.target_technique == "skip" or decision.aggressiveness_ratio == 0.0:
            if decision.target_technique == "whitespace_only":
                content = re.sub(r"\n{3,}", "\n\n", text)
                content = re.sub(r" {2,}", " ", content)
                return content.strip()
            return text

        if decision.target_technique == "ml_semantic" and self.llmlingua_engine:
            try:
                compressed = self.llmlingua_engine.compress_prompt(
                    text,
                    rate=1.0 - decision.aggressiveness_ratio,
                    force_tokens=[".", "!", "?", "\n"],
                )
                return str(compressed["compressed_prompt"])
            except Exception:
                pass  # fallback to heuristic

        # Heuristic fallback
        content = text
        content = re.sub(r"\n{3,}", "\n\n", content)
        content = re.sub(r" {2,}", " ", content)

        filler_patterns = [
            r"\b(?:please|kindly|would you|could you)\b",
            r"\b(?:I think|I believe|in my opinion)\b",
            r"\b(?:basically|essentially|fundamentally)\b",
        ]
        for pattern in filler_patterns:
            content = re.sub(pattern, "", content, flags=re.IGNORECASE)

        msg_tokens = count_tokens(content, self.model)
        if msg_tokens > decision.target_tokens:
            content = truncate_to_tokens(content, decision.target_tokens, self.model)

        return content.strip()


class PassThroughEvaluator(Evaluator):
    """Always passes fidelity check if no evaluator is injected."""

    def evaluate(self, original_text: str, optimized_text: str) -> FidelityResult:
        return FidelityResult(
            passed=True,
            overall_score=1.0,
            semantic_similarity=1.0,
            structural_integrity=1.0,
            details={"note": "fail-open passthrough evaluator"},
            is_passthrough=True,
        )
