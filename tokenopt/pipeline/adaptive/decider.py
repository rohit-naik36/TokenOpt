"""Decision matrix for adaptive compression."""

from __future__ import annotations

from tokenopt.pipeline.adaptive.contracts import CompressionDecision, CompressionProfile


class Decider:
    """Maps CompressionProfiles to CompressionDecisions."""

    def decide(self, profile: CompressionProfile) -> CompressionDecision:
        # P0: Absolute preservation rules based on flags
        if "IS_LAST_USER_QUERY" in profile.preservation_flags or "IS_SYSTEM_PROMPT" in profile.preservation_flags:
            return CompressionDecision(
                target_technique="skip",
                aggressiveness_ratio=0.0,
                target_tokens=profile.token_count,
                retry_budget=0
            )

        if "CONTAINS_CODE" in profile.preservation_flags or "CONTAINS_STRUCTURED_DATA" in profile.preservation_flags:
            return CompressionDecision(
                target_technique="whitespace_only",
                aggressiveness_ratio=0.0, # Do not truncate, only strip space safely
                target_tokens=profile.token_count,
                retry_budget=0
            )

        # Risk-based targeting
        if profile.risk_score < 0.2 and profile.compressibility > 0.5:
            # Low risk, highly compressible
            aggressiveness = 0.6 # target 60% reduction
            technique = "ml_semantic"
            retry_budget = 3
        elif profile.risk_score < 0.5:
            # Moderate risk
            aggressiveness = 0.3 # target 30% reduction
            technique = "heuristic"
            retry_budget = 2
        else:
            # Conservative fallback
            aggressiveness = 0.0
            technique = "skip"
            retry_budget = 0

        target_tokens = int(profile.token_count * (1.0 - aggressiveness))

        return CompressionDecision(
            target_technique=technique,
            aggressiveness_ratio=aggressiveness,
            target_tokens=target_tokens,
            retry_budget=retry_budget
        )
