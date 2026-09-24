"""Preservation-aware transformation stage for TokenOpt.

This module implements the Transformation Control Boundary as specified in
Checkpoint 5 of the TokenOpt context preservation architecture.

Architectural invariant:
    "The transformer executes only the transformation decisions produced by
    the Candidate Planner. It does not independently decide what is safe to
    transform."

The TransformerStage:
- Reads the PreservationMap set by AnalyzerStage on ``ctx.preservation_map``.
- Runs the CandidatePlanner to obtain an immutable CandidatePlan.
- Iterates over messages and applies the plan:
    * COMPRESS candidate  → delegates to ``compress_message_content``
    * REMOVE  candidate   → omits the message
    * Protected / unknown → passes the message through unchanged
- Records plan metrics on ``ctx.metrics``.

The transformer MUST NOT independently classify content.
The transformer MUST NOT introduce new preservation heuristics.

MVP boundary — span-level transformation is NOT implemented:
    Mixed-content messages (e.g., "Deploy version 4.2 to staging. Thanks.")
    are treated as an atomic unit.  If the Analyzer classifies the whole
    message as protected, the entire message remains unchanged.  Span-level
    segmentation and reconstruction is documented as a future capability.
"""

from __future__ import annotations

from typing import Any

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.base import OptimizationContext, PipelineStage
from tokenopt.pipeline.compressor import compress_message_content
from tokenopt.pipeline.planner import CandidatePlan, CandidatePlanner, CandidateType


class TransformerStage(PipelineStage):
    """Apply CandidatePlan transformation decisions to the message list.

    This stage enforces the preservation contract by executing only the
    transformations authorized by the CandidatePlanner.  It does not
    independently decide what is safe to transform.

    Transformation rules (applied per message index):
        P0 / P1 → always protected → pass through unchanged
        P2 COMPRESS candidate → delegate to ``compress_message_content``
        P2 protected → pass through unchanged
        P3 REMOVE candidate → omit from output
        P3 protected → pass through unchanged
        Unknown / no plan entry → fail-safe → pass through unchanged
    """

    name = "transformer"

    def __init__(self, config: TokenOptConfig | None = None) -> None:
        self.config: TokenOptConfig = config or TokenOptConfig()
        self._planner = CandidatePlanner(config=self.config)

    def process(self, ctx: OptimizationContext) -> OptimizationContext:
        """Execute CandidatePlan decisions against the message list.

        If no PreservationMap is available on the context (e.g., AnalyzerStage
        was not included in the pipeline), the stage fails safe: all messages
        are passed through unchanged and a metric is recorded.
        """
        if ctx.preservation_map is None:
            # No plan possible without a PreservationMap — fail safe.
            ctx.metrics["transformer_skipped"] = "no_preservation_map"
            ctx.metadata["surviving_indices"] = list(range(len(ctx.messages)))
            return ctx

        plan: CandidatePlan = self._planner.plan(ctx.preservation_map)

        transformed: list[dict[str, Any]] = []
        surviving_indices: list[int] = []

        target_tokens = int(
            ctx.original_token_count * ctx.config.compression_ratio
        )

        compress_count = 0
        remove_count = 0
        protected_count = 0

        for idx, msg in enumerate(ctx.messages):
            candidate = plan.get_candidate_for_message(idx)

            if candidate is None:
                # No plan entry: protected by fail-safe.
                transformed.append(msg)
                surviving_indices.append(idx)
                protected_count += 1
                continue

            if candidate.candidate_type == CandidateType.COMPRESS:
                # Delegate to the shared compression engine.
                transformed.append(
                    compress_message_content(msg, target_tokens, ctx.model)
                )
                surviving_indices.append(idx)
                compress_count += 1

            elif candidate.candidate_type == CandidateType.REMOVE:
                # Omit the message — do not append it to the output.
                remove_count += 1

            else:
                # Defensive fallback for any unknown future CandidateType.
                transformed.append(msg)
                surviving_indices.append(idx)
                protected_count += 1

        ctx.messages = transformed
        ctx.metadata["surviving_indices"] = surviving_indices

        ctx.metrics["transformer_applied"] = True
        ctx.metrics["compression_applied"] = True
        ctx.metrics["transformer_compress_count"] = compress_count
        ctx.metrics["transformer_remove_count"] = remove_count
        ctx.metrics["transformer_protected_count"] = protected_count
        ctx.metrics["transformer_plan_candidates"] = len(plan.candidates)
        ctx.metrics["transformer_plan_protected"] = len(plan.protected_units)

        return ctx

    @property
    def planner(self) -> CandidatePlanner:
        """Expose the internal planner for introspection in tests."""
        return self._planner
