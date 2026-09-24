"""Tests for TransformerStage (Checkpoint 5: Preservation-Aware Transformation).

Proves the architectural invariant:
    "The transformer executes only the transformation decisions produced by
    the Candidate Planner. It does not independently decide what is safe to
    transform."

Test inventory:
1.  P0 protected unit: compressor not invoked; output exactly unchanged.
2.  P1 protected unit: compressor not invoked; output exactly unchanged.
3.  P2 COMPRESS candidate: compressor invoked; transformed result returned.
4.  P2 protected (ineligible): compressor not invoked; output unchanged.
5.  P3 REMOVE candidate: message omitted from output.
6.  P3 protected (ineligible): message unchanged.
7.  Unknown/unsupported preservation state: fail-safe; message unchanged.
8.  No PreservationMap on context: fail-safe; all messages unchanged.
9.  Mixed message list: per-index decisions applied independently.
10. Planner → transformer integration: transformation follows CandidatePlan.
11. Transformer does not independently classify content (spy-based).
12. Non-string message content passes through unchanged for COMPRESS.
13. REMOVE on multiple messages removes all of them.
14. Empty message list produces empty output.
15. plan metrics recorded on ctx.metrics.
16. Production pipeline integration: BaseOptimizedClient & _build_pipeline.
"""

from __future__ import annotations

from unittest.mock import patch

from tokenopt.clients.local_client import LocalClient
from tokenopt.clients.openai_client import OpenAI
from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.analyzer import AnalyzerStage
from tokenopt.pipeline.base import OptimizationContext, OptimizationPipeline
from tokenopt.pipeline.compressor import CompressorStage, compress_message_content
from tokenopt.pipeline.planner import (
    CandidatePlan,
    CandidatePlanner,
)
from tokenopt.pipeline.preservation import (
    ContextUnit,
    DetectionCertainty,
    PreservationClass,
    PreservationMap,
    PreservedInvariant,
    StructuralType,
    TransformationEligibility,
)
from tokenopt.pipeline.transformer import TransformerStage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MODEL = "gpt-4o"


def _make_config(**kwargs: object) -> TokenOptConfig:
    return TokenOptConfig(**kwargs)  # type: ignore[arg-type]


def _make_ctx(
    messages: list[dict],
    preservation_map: PreservationMap | None = None,
    config: TokenOptConfig | None = None,
) -> OptimizationContext:
    cfg = config or _make_config()
    ctx = OptimizationContext(
        messages=messages,
        model=MODEL,
        config=cfg,
    )
    ctx.preservation_map = preservation_map
    return ctx


def _make_eligibility(
    *,
    allow_compression: bool = False,
    allow_removal: bool = False,
) -> TransformationEligibility:
    return TransformationEligibility(
        allow_lossless_normalization=False,
        allow_meaning_preserving_compression=allow_compression,
        allow_removal=allow_removal,
        allow_truncation=False,
    )


def _make_unit(
    message_index: int,
    role: str = "user",
    preservation_class: PreservationClass = PreservationClass.P2_COMPRESSIBLE,
    *,
    allow_compression: bool = False,
    allow_removal: bool = False,
    invariants: tuple[PreservedInvariant, ...] = (),
) -> ContextUnit:
    return ContextUnit(
        message_index=message_index,
        role=role,
        structural_type=StructuralType.PROSE,
        detection_certainty=DetectionCertainty.DETECTED,
        preservation_class=preservation_class,
        eligibility=_make_eligibility(
            allow_compression=allow_compression,
            allow_removal=allow_removal,
        ),
        invariants=invariants,
    )


def _make_pmap(*units: ContextUnit) -> PreservationMap:
    return PreservationMap(units=tuple(units))


def _make_plan_from_pmap(pmap: PreservationMap) -> CandidatePlan:
    return CandidatePlanner().plan(pmap)


# ---------------------------------------------------------------------------
# 1. P0 protected unit: compressor not invoked; output exactly unchanged.
# ---------------------------------------------------------------------------


class TestP0Protected:
    """P0 authority units must never be transformed."""

    def test_p0_output_exactly_unchanged(self) -> None:
        """1. P0 protected: message content is byte-for-byte identical to input."""
        original_content = "You are a production database specialist. Follow Level-4."
        messages = [{"role": "system", "content": original_content}]

        unit = _make_unit(
            0,
            role="system",
            preservation_class=PreservationClass.P0_AUTHORITY,
        )
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        stage = TransformerStage()
        result = stage.process(ctx)

        assert result.messages[0]["content"] == original_content
        assert len(result.messages) == 1

    def test_p0_compress_message_content_not_invoked(self) -> None:
        """1. P0 protected: compress_message_content must not be called."""
        messages = [{"role": "system", "content": "Authority content."}]
        unit = _make_unit(0, role="system", preservation_class=PreservationClass.P0_AUTHORITY)
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        with patch(
            "tokenopt.pipeline.transformer.compress_message_content"
        ) as mock_compress:
            TransformerStage().process(ctx)
            mock_compress.assert_not_called()


# ---------------------------------------------------------------------------
# 2. P1 protected unit: compressor not invoked; output exactly unchanged.
# ---------------------------------------------------------------------------


class TestP1Protected:
    """P1 information units must never be transformed."""

    def test_p1_output_exactly_unchanged(self) -> None:
        """2. P1 protected: message content is byte-for-byte identical to input."""
        original_content = (
            'SELECT id, name FROM users WHERE active = TRUE;\n-- Important query'
        )
        messages = [{"role": "user", "content": original_content}]

        unit = _make_unit(
            0,
            preservation_class=PreservationClass.P1_INFORMATION,
        )
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        stage = TransformerStage()
        result = stage.process(ctx)

        assert result.messages[0]["content"] == original_content
        assert len(result.messages) == 1

    def test_p1_compress_message_content_not_invoked(self) -> None:
        """2. P1 protected: compress_message_content must not be called."""
        messages = [{"role": "user", "content": "Critical information here."}]
        unit = _make_unit(0, preservation_class=PreservationClass.P1_INFORMATION)
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        with patch(
            "tokenopt.pipeline.transformer.compress_message_content"
        ) as mock_compress:
            TransformerStage().process(ctx)
            mock_compress.assert_not_called()


# ---------------------------------------------------------------------------
# 3. P2 COMPRESS candidate: compressor invoked; transformed result returned.
# ---------------------------------------------------------------------------


class TestP2CompressCandidate:
    """P2 COMPRESS candidates must be passed to compress_message_content."""

    def test_p2_compress_invokes_compression_engine(self) -> None:
        """3. P2 COMPRESS: compress_message_content is called exactly once."""
        messages = [{"role": "user", "content": "Please   help me understand this."}]
        unit = _make_unit(
            0, preservation_class=PreservationClass.P2_COMPRESSIBLE, allow_compression=True
        )
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        with patch(
            "tokenopt.pipeline.transformer.compress_message_content",
            wraps=compress_message_content,
        ) as spy:
            TransformerStage().process(ctx)
            spy.assert_called_once()

    def test_p2_compress_result_is_returned(self) -> None:
        """3. P2 COMPRESS: the transformed content replaces the original."""
        content = "Please   help me   understand this.   "
        messages = [{"role": "user", "content": content}]
        unit = _make_unit(
            0, preservation_class=PreservationClass.P2_COMPRESSIBLE, allow_compression=True
        )
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        stage = TransformerStage()
        result = stage.process(ctx)

        # Compression normalizes excessive whitespace — result differs from input.
        assert result.messages[0]["content"] != content
        assert len(result.messages) == 1

    def test_p2_compress_metric_recorded(self) -> None:
        """3. P2 COMPRESS: compress count metric is incremented."""
        messages = [{"role": "user", "content": "Basically, just help me."}]
        unit = _make_unit(
            0, preservation_class=PreservationClass.P2_COMPRESSIBLE, allow_compression=True
        )
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        result = TransformerStage().process(ctx)
        assert result.metrics["transformer_compress_count"] == 1
        assert result.metrics["transformer_remove_count"] == 0


# ---------------------------------------------------------------------------
# 4. P2 protected (ineligible): compressor not invoked; output unchanged.
# ---------------------------------------------------------------------------


class TestP2Protected:
    """P2 units without compression eligibility must not be transformed."""

    def test_p2_ineligible_output_unchanged(self) -> None:
        """4. P2 ineligible: output is exactly the same as input."""
        original_content = "Deploy version 4.2 to staging. Thanks."
        messages = [{"role": "user", "content": original_content}]

        unit = _make_unit(
            0,
            preservation_class=PreservationClass.P2_COMPRESSIBLE,
            allow_compression=False,  # ineligible
        )
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        result = TransformerStage().process(ctx)

        assert result.messages[0]["content"] == original_content
        assert len(result.messages) == 1

    def test_p2_ineligible_compress_not_invoked(self) -> None:
        """4. P2 ineligible: compress_message_content must not be called."""
        messages = [{"role": "user", "content": "Some message."}]
        unit = _make_unit(
            0, preservation_class=PreservationClass.P2_COMPRESSIBLE, allow_compression=False
        )
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        with patch(
            "tokenopt.pipeline.transformer.compress_message_content"
        ) as mock_compress:
            TransformerStage().process(ctx)
            mock_compress.assert_not_called()


# ---------------------------------------------------------------------------
# 5. P3 REMOVE candidate: message omitted from output.
# ---------------------------------------------------------------------------


class TestP3RemoveCandidate:
    """P3 REMOVE candidates must be omitted entirely from the output."""

    def test_p3_remove_omits_single_message(self) -> None:
        """5. P3 REMOVE: sole message is removed when planner designates REMOVE."""
        messages = [{"role": "user", "content": "Okay!"}]
        unit = _make_unit(
            0, preservation_class=PreservationClass.P3_REMOVABLE, allow_removal=True
        )
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        result = TransformerStage().process(ctx)

        # Transformer must NOT override planner based on message count: output is empty.
        assert result.messages == []
        assert result.metrics["transformer_remove_count"] == 1

    def test_p3_remove_omits_message(self) -> None:
        """5. P3 REMOVE: message is not present in output."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Sure!"},
        ]
        unit_0 = _make_unit(0, role="system", preservation_class=PreservationClass.P0_AUTHORITY)
        unit_1 = _make_unit(
            1, preservation_class=PreservationClass.P3_REMOVABLE, allow_removal=True
        )
        pmap = _make_pmap(unit_0, unit_1)
        ctx = _make_ctx(messages, pmap)

        result = TransformerStage().process(ctx)

        assert len(result.messages) == 1
        assert result.messages[0]["content"] == "You are a helpful assistant."
        assert result.metrics["transformer_remove_count"] == 1

    def test_all_messages_removable_produces_empty_output(self) -> None:
        """5. P3 REMOVE: if all messages are removable, output is empty (no silent restore)."""
        messages = [
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        unit_0 = _make_unit(
            0, preservation_class=PreservationClass.P3_REMOVABLE, allow_removal=True
        )
        unit_1 = _make_unit(
            1,
            role="assistant",
            preservation_class=PreservationClass.P3_REMOVABLE,
            allow_removal=True,
        )
        pmap = _make_pmap(unit_0, unit_1)
        ctx = _make_ctx(messages, pmap)

        result = TransformerStage().process(ctx)

        # Must NOT silently restore original messages when all are removable.
        assert result.messages == []
        assert result.metrics["transformer_remove_count"] == 2

    def test_mixed_protected_p1_and_removable_p3(self) -> None:
        """5. P3 REMOVE: protected P1 remains exactly unchanged, P3 is removed."""
        p1_code = "```python\ndef test(): pass\n```"
        messages = [
            {"role": "user", "content": p1_code},
            {"role": "user", "content": "Thanks!"},
        ]
        unit_0 = _make_unit(
            0,
            preservation_class=PreservationClass.P1_INFORMATION,
        )
        unit_1 = _make_unit(
            1, preservation_class=PreservationClass.P3_REMOVABLE, allow_removal=True
        )
        pmap = _make_pmap(unit_0, unit_1)
        ctx = _make_ctx(messages, pmap)

        result = TransformerStage().process(ctx)

        assert len(result.messages) == 1
        assert result.messages[0]["content"] == p1_code
        assert result.metrics["transformer_remove_count"] == 1
        assert result.metrics["transformer_protected_count"] == 1

    def test_planner_authority_no_message_count_override(self) -> None:
        """5. P3 REMOVE: transformer strictly obeys CandidatePlan without message-count checks."""
        messages = [{"role": "user", "content": "Sure."}]
        unit = _make_unit(
            0, preservation_class=PreservationClass.P3_REMOVABLE, allow_removal=True
        )
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        stage = TransformerStage()
        result = stage.process(ctx)

        # Proves transformer does not override plan decisions based on len(messages)
        assert len(result.messages) == 0
        assert result.metrics["transformer_remove_count"] == 1


# ---------------------------------------------------------------------------
# 6. P3 protected (ineligible): message unchanged.
# ---------------------------------------------------------------------------


class TestP3Protected:
    """P3 units without removal eligibility must remain in the output unchanged."""

    def test_p3_ineligible_message_unchanged(self) -> None:
        """6. P3 ineligible: message content preserved exactly."""
        original_content = "Thank you very much."
        messages = [{"role": "user", "content": original_content}]

        unit = _make_unit(
            0,
            preservation_class=PreservationClass.P3_REMOVABLE,
            allow_removal=False,  # ineligible
        )
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        result = TransformerStage().process(ctx)

        assert len(result.messages) == 1
        assert result.messages[0]["content"] == original_content


# ---------------------------------------------------------------------------
# 7. Unknown/unsupported preservation state: fail-safe; message unchanged.
# ---------------------------------------------------------------------------


class TestUnknownPreservationState:
    """Unknown preservation classes must be fail-safe protected."""

    def test_unknown_class_message_unchanged(self) -> None:
        """7. Unknown class: message passes through unchanged."""
        original_content = "Some message with an unknown preservation class."
        messages = [{"role": "user", "content": original_content}]

        # Build a unit, then bypass the enum to set an unknown class value.
        unit = _make_unit(0, preservation_class=PreservationClass.P2_COMPRESSIBLE)
        object.__setattr__(unit, "preservation_class", "FUTURE_UNKNOWN_CLASS")
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        result = TransformerStage().process(ctx)

        assert len(result.messages) == 1
        assert result.messages[0]["content"] == original_content

    def test_unknown_class_compress_not_invoked(self) -> None:
        """7. Unknown class: compress_message_content must not be called."""
        messages = [{"role": "user", "content": "Unknown class message."}]
        unit = _make_unit(0, preservation_class=PreservationClass.P2_COMPRESSIBLE)
        object.__setattr__(unit, "preservation_class", "FUTURE_UNKNOWN_CLASS")
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        with patch(
            "tokenopt.pipeline.transformer.compress_message_content"
        ) as mock_compress:
            TransformerStage().process(ctx)
            mock_compress.assert_not_called()


# ---------------------------------------------------------------------------
# 8. No PreservationMap on context: fail-safe; all messages unchanged.
# ---------------------------------------------------------------------------


class TestNoPreservationMap:
    """Without a PreservationMap, the transformer must be a no-op."""

    def test_no_preservation_map_all_messages_unchanged(self) -> None:
        """8. No PreservationMap: all messages pass through unchanged."""
        messages = [
            {"role": "system", "content": "You are an assistant."},
            {"role": "user", "content": "Hello!"},
        ]
        ctx = _make_ctx(messages, preservation_map=None)

        result = TransformerStage().process(ctx)

        assert len(result.messages) == 2
        assert result.messages[0]["content"] == "You are an assistant."
        assert result.messages[1]["content"] == "Hello!"

    def test_no_preservation_map_metric_recorded(self) -> None:
        """8. No PreservationMap: skipped metric is set."""
        ctx = _make_ctx([{"role": "user", "content": "Hi."}], preservation_map=None)

        result = TransformerStage().process(ctx)

        assert result.metrics.get("transformer_skipped") == "no_preservation_map"
        assert "transformer_applied" not in result.metrics


# ---------------------------------------------------------------------------
# 9. Mixed message list: per-index decisions applied independently.
# ---------------------------------------------------------------------------


class TestMixedMessageList:
    """Decisions are applied independently per message index."""

    def test_mixed_plan_applied_per_index(self) -> None:
        """9. Mixed list: P0 unchanged, P2 COMPRESS transformed, P3 REMOVE omitted."""
        messages = [
            {"role": "system", "content": "You are a system."},
            {"role": "user", "content": "Please   explain this."},
            {"role": "assistant", "content": "Thanks!"},
        ]

        unit_sys = _make_unit(0, role="system", preservation_class=PreservationClass.P0_AUTHORITY)
        unit_user = _make_unit(
            1, preservation_class=PreservationClass.P2_COMPRESSIBLE, allow_compression=True
        )
        unit_asst = _make_unit(
            2, preservation_class=PreservationClass.P3_REMOVABLE, allow_removal=True
        )

        pmap = _make_pmap(unit_sys, unit_user, unit_asst)
        ctx = _make_ctx(messages, pmap)

        result = TransformerStage().process(ctx)

        # P3 REMOVE: assistant message omitted → 2 messages remain
        assert len(result.messages) == 2
        # P0: system message unchanged
        assert result.messages[0]["content"] == "You are a system."
        # P2 COMPRESS: whitespace normalized, filler removed
        assert result.messages[1]["content"] != "Please   explain this."
        # Metrics
        assert result.metrics["transformer_compress_count"] == 1
        assert result.metrics["transformer_remove_count"] == 1

    def test_mixed_no_candidate_entry_is_protected(self) -> None:
        """9. Message with no plan entry is protected by fail-safe."""
        messages = [
            {"role": "user", "content": "First."},
            {"role": "user", "content": "Second — no plan entry."},
        ]
        # Only unit for index 0
        unit = _make_unit(
            0, preservation_class=PreservationClass.P2_COMPRESSIBLE, allow_compression=True
        )
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        result = TransformerStage().process(ctx)

        # Index 1 has no plan entry → fail-safe protected
        assert len(result.messages) == 2
        assert result.messages[1]["content"] == "Second — no plan entry."


# ---------------------------------------------------------------------------
# 10. Planner → transformer integration: transformation follows CandidatePlan.
# ---------------------------------------------------------------------------


class TestPlannerTransformerIntegration:
    """End-to-end: AnalyzerStage + TransformerStage in the same pipeline."""

    def test_analyzer_transformer_pipeline_integration(self) -> None:
        """10. AnalyzerStage sets preservation_map; TransformerStage reads it."""
        config = TokenOptConfig()
        messages = [
            {"role": "system", "content": "You are a database specialist on prod-db-01."},
            {"role": "user", "content": "Please   explain this query."},
        ]

        pipeline = OptimizationPipeline(
            [AnalyzerStage(config), TransformerStage(config)],
            config,
        )
        ctx = pipeline.run(messages, MODEL)

        # Transformer ran (preservation_map was available)
        assert ctx.preservation_map is not None
        assert "transformer_applied" in ctx.metrics or "transformer_skipped" in ctx.metrics
        # System message with prod-db-01 → protected; content unchanged
        assert "prod-db-01" in ctx.messages[0]["content"]

    def test_transformer_decision_follows_plan_not_self_classification(self) -> None:
        """10. TransformerStage calls CandidatePlanner.plan() — decisions come from plan."""
        messages = [{"role": "user", "content": "Please help me."}]
        unit = _make_unit(
            0, preservation_class=PreservationClass.P2_COMPRESSIBLE, allow_compression=True
        )
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        stage = TransformerStage()

        # Spy on the internal planner to confirm it is called
        original_plan = stage.planner.plan
        plan_calls: list[PreservationMap] = []

        def spy_plan(pm: PreservationMap) -> CandidatePlan:
            plan_calls.append(pm)
            return original_plan(pm)

        stage._planner.plan = spy_plan  # type: ignore[method-assign]
        stage.process(ctx)

        assert len(plan_calls) == 1
        assert plan_calls[0] is pmap


# ---------------------------------------------------------------------------
# 11. Transformer does not independently classify content (spy-based).
# ---------------------------------------------------------------------------


class TestNoIndependentClassification:
    """The transformer must not contain its own preservation classification logic."""

    def test_transformer_does_not_call_detect_structure(self) -> None:
        """11. detect_structure from analyzer is not called by the transformer."""
        messages = [{"role": "user", "content": "```python\nprint('hi')\n```"}]
        unit = _make_unit(
            0, preservation_class=PreservationClass.P2_COMPRESSIBLE, allow_compression=True
        )
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        with patch("tokenopt.pipeline.analyzer.detect_structure") as mock_detect:
            TransformerStage().process(ctx)
            mock_detect.assert_not_called()

    def test_transformer_does_not_call_extract_invariants(self) -> None:
        """11. extract_invariants from analyzer is not called by the transformer."""
        messages = [{"role": "user", "content": "See cluster-01 for details."}]
        unit = _make_unit(
            0, preservation_class=PreservationClass.P2_COMPRESSIBLE, allow_compression=True
        )
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        with patch("tokenopt.pipeline.analyzer.extract_invariants") as mock_extract:
            TransformerStage().process(ctx)
            mock_extract.assert_not_called()

    def test_transformer_respects_plan_over_content_inspection(self) -> None:
        """11. A P2 COMPRESS unit with 'protected-looking' content is compressed per plan."""
        # Content that looks like it contains invariants — but the plan says COMPRESS.
        content = "See cluster-prod-01 at https://api.internal/v1 for version 3.2."
        messages = [{"role": "user", "content": content}]
        unit = _make_unit(
            0, preservation_class=PreservationClass.P2_COMPRESSIBLE, allow_compression=True
        )
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        with patch(
            "tokenopt.pipeline.transformer.compress_message_content",
            wraps=compress_message_content,
        ) as spy:
            TransformerStage().process(ctx)
            # Transformer delegated to compressor because the PLAN said COMPRESS
            spy.assert_called_once()


# ---------------------------------------------------------------------------
# 12. Non-string message content passes through unchanged for COMPRESS.
# ---------------------------------------------------------------------------


class TestNonStringContent:
    """Non-string content values must be preserved exactly (e.g., vision payloads)."""

    def test_non_string_content_compress_candidate_unchanged(self) -> None:
        """12. Non-string content: even COMPRESS candidate is returned as-is."""
        vision_content = [{"type": "image_url", "image_url": {"url": "https://example.com/img.png"}}]
        messages = [{"role": "user", "content": vision_content}]
        unit = _make_unit(
            0, preservation_class=PreservationClass.P2_COMPRESSIBLE, allow_compression=True
        )
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        result = TransformerStage().process(ctx)

        assert result.messages[0]["content"] == vision_content


# ---------------------------------------------------------------------------
# 13. REMOVE on multiple messages removes all of them.
# ---------------------------------------------------------------------------


class TestMultipleRemoval:
    """All messages designated as REMOVE candidates must be omitted."""

    def test_multiple_remove_candidates_all_omitted(self) -> None:
        """13. Multiple P3 REMOVE candidates: all removed, other messages preserved."""
        messages = [
            {"role": "system", "content": "Authority."},
            {"role": "user", "content": "Sure!"},
            {"role": "assistant", "content": "Okay."},
            {"role": "user", "content": "Proceed with the plan."},
        ]

        unit_0 = _make_unit(0, role="system", preservation_class=PreservationClass.P0_AUTHORITY)
        unit_1 = _make_unit(
            1, preservation_class=PreservationClass.P3_REMOVABLE, allow_removal=True
        )
        unit_2 = _make_unit(
            2,
            role="assistant",
            preservation_class=PreservationClass.P3_REMOVABLE,
            allow_removal=True,
        )
        unit_3 = _make_unit(
            3, preservation_class=PreservationClass.P2_COMPRESSIBLE, allow_compression=True
        )

        pmap = _make_pmap(unit_0, unit_1, unit_2, unit_3)
        ctx = _make_ctx(messages, pmap)

        result = TransformerStage().process(ctx)

        assert len(result.messages) == 2
        assert result.messages[0]["content"] == "Authority."
        assert "Proceed" in result.messages[1]["content"]
        assert result.metrics["transformer_remove_count"] == 2


# ---------------------------------------------------------------------------
# 14. Empty message list produces empty output.
# ---------------------------------------------------------------------------


class TestEmptyMessages:
    """Empty input must produce empty output without errors."""

    def test_empty_messages_empty_output(self) -> None:
        """14. Empty message list: empty output, no errors."""
        pmap = PreservationMap(units=())
        ctx = _make_ctx([], pmap)

        result = TransformerStage().process(ctx)

        assert result.messages == []
        assert result.metrics.get("transformer_applied") is True


# ---------------------------------------------------------------------------
# 15. Plan metrics recorded on ctx.metrics.
# ---------------------------------------------------------------------------


class TestMetrics:
    """TransformerStage records plan metrics for observability."""

    def test_metrics_recorded_after_transformation(self) -> None:
        """15. Metrics: all plan metric keys present after transformation."""
        messages = [
            {"role": "system", "content": "Authority."},
            {"role": "user", "content": "Basically, please explain."},
        ]
        unit_0 = _make_unit(0, role="system", preservation_class=PreservationClass.P0_AUTHORITY)
        unit_1 = _make_unit(
            1, preservation_class=PreservationClass.P2_COMPRESSIBLE, allow_compression=True
        )
        pmap = _make_pmap(unit_0, unit_1)
        ctx = _make_ctx(messages, pmap)

        result = TransformerStage().process(ctx)

        assert result.metrics["transformer_applied"] is True
        assert isinstance(result.metrics["transformer_compress_count"], int)
        assert isinstance(result.metrics["transformer_remove_count"], int)
        assert isinstance(result.metrics["transformer_protected_count"], int)
        assert isinstance(result.metrics["transformer_plan_candidates"], int)
        assert isinstance(result.metrics["transformer_plan_protected"], int)

    def test_metrics_counts_are_correct(self) -> None:
        """15. Metrics: counts match actual plan decisions."""
        messages = [
            {"role": "system", "content": "Protected."},
            {"role": "user", "content": "Compress this."},
            {"role": "user", "content": "Remove this filler."},
        ]
        unit_0 = _make_unit(0, role="system", preservation_class=PreservationClass.P0_AUTHORITY)
        unit_1 = _make_unit(
            1, preservation_class=PreservationClass.P2_COMPRESSIBLE, allow_compression=True
        )
        unit_2 = _make_unit(
            2, preservation_class=PreservationClass.P3_REMOVABLE, allow_removal=True
        )
        pmap = _make_pmap(unit_0, unit_1, unit_2)
        ctx = _make_ctx(messages, pmap)

        result = TransformerStage().process(ctx)

        assert result.metrics["transformer_compress_count"] == 1
        assert result.metrics["transformer_remove_count"] == 1
        # P0 is a protected_unit in the plan → counted as protected
        assert result.metrics["transformer_protected_count"] == 1


# ---------------------------------------------------------------------------
# 16. Production pipeline integration: BaseOptimizedClient & _build_pipeline
# ---------------------------------------------------------------------------


class TestProductionPipelineIntegration:
    """Proves the REAL production TokenOpt client pipeline uses TransformerStage."""

    def test_production_pipeline_registration(self) -> None:
        """Test A: BaseOptimizedClient pipeline contains AnalyzerStage and
        TransformerStage; CompressorStage is NOT present as the transformation stage.
        """
        # Test with OpenAI client
        client_openai = OpenAI(api_key="test-key")
        openai_stages = client_openai.pipeline.stages
        openai_names = [s.name for s in openai_stages]

        assert any(isinstance(s, AnalyzerStage) for s in openai_stages)
        assert any(isinstance(s, TransformerStage) for s in openai_stages)
        assert not any(isinstance(s, CompressorStage) for s in openai_stages)
        assert "analyzer" in openai_names
        assert "transformer" in openai_names
        assert "compressor" not in openai_names

        # Test with LocalClient (stub _create_client to avoid requiring optional ollama)
        with patch.object(LocalClient, "_create_client", return_value=object()):
            client_local = LocalClient(api_key="test-key")
            local_stages = client_local.pipeline.stages
            local_names = [s.name for s in local_stages]

            assert any(isinstance(s, AnalyzerStage) for s in local_stages)
            assert any(isinstance(s, TransformerStage) for s in local_stages)
            assert not any(isinstance(s, CompressorStage) for s in local_stages)
            assert "analyzer" in local_names
            assert "transformer" in local_names
            assert "compressor" not in local_names

    def test_protected_content_survives_production_path(self) -> None:
        """Test B: P1 protected content survives production pipeline execution exactly."""
        client = OpenAI(api_key="test-key")
        # Code block containing Python code with whitespace and formatting
        protected_code = (
            "```python\n"
            "def process_data(records):\n"
            "    # Critical invariant: must not be stripped or compressed\n"
            "    return [r['id'] for r in records if r.get('active')]\n"
            "```"
        )
        messages = [{"role": "user", "content": protected_code}]

        ctx = client.pipeline.run(messages, "gpt-4o")

        assert ctx.messages[0]["content"] == protected_code
        assert ctx.preservation_map is not None
        assert ctx.metrics.get("transformer_applied") is True
        assert ctx.metrics.get("transformer_compress_count") == 0
        assert ctx.metrics.get("transformer_protected_count") >= 1

    def test_eligible_p2_is_transformed_in_production_path(self) -> None:
        """Test C: Eligible P2 compressible content is transformed via production pipeline."""
        client = OpenAI(api_key="test-key")
        compressible_prose = (
            "Please   kindly explain    this topic. "
            "Basically, in my opinion, I believe it is essential."
        )
        messages = [{"role": "user", "content": compressible_prose}]

        ctx = client.pipeline.run(messages, "gpt-4o")

        # Transformation occurs: whitespace collapsed, filler removed
        assert ctx.messages[0]["content"] != compressible_prose
        assert "kindly" not in ctx.messages[0]["content"].lower()
        assert "basically" not in ctx.messages[0]["content"].lower()
        assert ctx.metrics.get("transformer_applied") is True
        assert ctx.metrics.get("transformer_compress_count") == 1

    def test_compression_disabled_in_production_path(self) -> None:
        """Test D: enable_compression=False prevents TransformerStage from transforming."""
        cfg = TokenOptConfig(enable_compression=False)
        client = OpenAI(api_key="test-key", config=cfg)
        compressible_prose = (
            "Please   kindly explain    this topic. "
            "Basically, in my opinion, I believe it is essential."
        )
        messages = [{"role": "user", "content": compressible_prose}]

        ctx = client.pipeline.run(messages, "gpt-4o")

        # When enable_compression=False, transformer is gated off by _should_run_stage
        assert ctx.messages[0]["content"] == compressible_prose
        assert "transformer_latency_ms" not in ctx.metrics
        assert "transformer_applied" not in ctx.metrics
