"""Bounded feedback loop orchestrator for adaptive compression."""

from __future__ import annotations

import time

from tokenopt.pipeline.adaptive.contracts import (
    CompressionDecision,
    Evaluator,
    Executor,
    OptimizationResult,
)


class AdaptiveCompressionLoop:
    """Manages the bounded retry loop for segment compression."""

    def __init__(
        self,
        executor: Executor,
        evaluator: Evaluator,
        min_token_savings: int = 50,
        max_latency_ms: float = 1000.0,
    ):
        self.executor = executor
        self.evaluator = evaluator
        self.min_token_savings = min_token_savings
        self.max_latency_ms = max_latency_ms

    def optimize_segment(self, text: str, initial_decision: CompressionDecision) -> OptimizationResult:
        """Run the bounded feedback loop on a segment."""

        # Fast path bypass
        if initial_decision.target_technique == "skip" or initial_decision.aggressiveness_ratio == 0.0:
            if initial_decision.target_technique == "whitespace_only":
                # execute whitespace strip immediately
                optimized = self.executor.execute(text, initial_decision)
                return OptimizationResult(
                    original_text=text,
                    optimized_text=optimized,
                    tokens_saved=0,  # Ignored for bypass
                    iterations=1,
                    final_fidelity=None
                )

            return OptimizationResult(
                original_text=text,
                optimized_text=text,
                tokens_saved=0,
                iterations=0,
                final_fidelity=None
            )

        start_time = time.perf_counter()

        decision = initial_decision

        for iteration in range(initial_decision.retry_budget + 1):
            # 1. Budget check
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            if elapsed_ms > self.max_latency_ms:
                break

            # 2. Execute
            candidate = self.executor.execute(text, decision)

            # Calculate mock savings based on length for now, in integration
            # this would use the real token counter.
            tokens_saved = len(text) - len(candidate)

            # 3. Evaluate
            fidelity = self.evaluator.evaluate(text, candidate)

            # 4. Accept / Retry
            if fidelity.passed:
                if tokens_saved >= self.min_token_savings:
                    return OptimizationResult(
                        original_text=text,
                        optimized_text=candidate,
                        tokens_saved=tokens_saved,
                        iterations=iteration + 1,
                        final_fidelity=fidelity
                    )
                else:
                    # Passed but not worth the overhead, fail-open
                    break
            else:
                # Failed fidelity, lower aggressiveness
                new_aggressiveness = decision.aggressiveness_ratio * 0.75
                if new_aggressiveness < 0.1:
                    break

                decision = CompressionDecision(
                    target_technique=decision.target_technique,
                    aggressiveness_ratio=new_aggressiveness,
                    target_tokens=int(decision.target_tokens * 1.2), # loosen target
                    retry_budget=decision.retry_budget - 1
                )

        # Exhausted budget or failed conditions -> fail-open
        return OptimizationResult(
            original_text=text,
            optimized_text=text,
            tokens_saved=0,
            iterations=initial_decision.retry_budget + 1,
            final_fidelity=None
        )
