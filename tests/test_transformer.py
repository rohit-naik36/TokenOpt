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
from tokenopt.pipeline.compressor import CompressorStage
from tokenopt.pipeline.planner import (
    CandidatePlan,
    CandidatePlanner,
)
from tokenopt.pipeline.preservation import (
    ContextUnit,
    DetectionCertainty,
    EntityCategory,
    InvariantType,
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

    def test_p0_compress_not_invoked(self) -> None:
        """1. P0 protected: prose transformation must not be called."""
        messages = [{"role": "system", "content": "Authority content."}]
        unit = _make_unit(0, role="system", preservation_class=PreservationClass.P0_AUTHORITY)
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        with patch.object(
            TransformerStage, "_transform_prose_message"
        ) as mock_transform:
            TransformerStage().process(ctx)
            mock_transform.assert_not_called()


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

    def test_p1_compress_not_invoked(self) -> None:
        """2. P1 protected: prose transformation must not be called."""
        messages = [{"role": "user", "content": "Critical information here."}]
        unit = _make_unit(0, preservation_class=PreservationClass.P1_INFORMATION)
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        with patch.object(
            TransformerStage, "_transform_prose_message"
        ) as mock_transform:
            TransformerStage().process(ctx)
            mock_transform.assert_not_called()


# ---------------------------------------------------------------------------
# 3. P2 COMPRESS candidate: compressor invoked; transformed result returned.
# ---------------------------------------------------------------------------


class TestP2CompressCandidate:
    """P2 COMPRESS candidates must be passed to prose transformation."""

    def test_p2_compress_invokes_compression_engine(self) -> None:
        """3. P2 COMPRESS: _transform_prose_message is called exactly once."""
        messages = [{"role": "user", "content": "Please   help me understand this."}]
        unit = _make_unit(
            0, preservation_class=PreservationClass.P2_COMPRESSIBLE, allow_compression=True
        )
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        with patch.object(
            TransformerStage,
            "_transform_prose_message",
            wraps=TransformerStage()._transform_prose_message,
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
        """4. P2 ineligible: prose transformation must not be called."""
        messages = [{"role": "user", "content": "Some message."}]
        unit = _make_unit(
            0, preservation_class=PreservationClass.P2_COMPRESSIBLE, allow_compression=False
        )
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        with patch.object(
            TransformerStage, "_transform_prose_message"
        ) as mock_transform:
            TransformerStage().process(ctx)
            mock_transform.assert_not_called()


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
        """7. Unknown class: prose transformation must not be called."""
        messages = [{"role": "user", "content": "Unknown class message."}]
        unit = _make_unit(0, preservation_class=PreservationClass.P2_COMPRESSIBLE)
        object.__setattr__(unit, "preservation_class", "FUTURE_UNKNOWN_CLASS")
        pmap = _make_pmap(unit)
        ctx = _make_ctx(messages, pmap)

        with patch.object(
            TransformerStage, "_transform_prose_message"
        ) as mock_transform:
            TransformerStage().process(ctx)
            mock_transform.assert_not_called()


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

        stage._planner.plan = spy_plan  # type: ignore[method-assign,assignment]
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

        with patch.object(
            TransformerStage,
            "_transform_prose_message",
            wraps=TransformerStage()._transform_prose_message,
        ) as spy:
            TransformerStage().process(ctx)
            # Transformer delegated to prose transformation because the PLAN said COMPRESS
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
        val = ctx.metrics.get("transformer_protected_count")
        assert val is not None and val >= 1

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


# =============================================================================
# Checkpoint 7: Deterministic Preservation-Aware Transformation Tests
# =============================================================================

class TestCP7Eligibility:
    """Eligibility rules: only P2 COMPRESS PROSE units are transformed."""

    def test_p0_authority_remains_strictly_unchanged(self) -> None:
        """P0 authority units pass through byte-for-byte unchanged."""
        raw = "You are a secure system coordinator. Please follow protocol."
        messages = [{"role": "system", "content": raw}]
        unit = _make_unit(0, role="system", preservation_class=PreservationClass.P0_AUTHORITY)
        ctx = _make_ctx(messages, _make_pmap(unit))

        res = TransformerStage().process(ctx)
        assert res.messages[0]["content"] == raw

    def test_p1_information_remains_strictly_unchanged(self) -> None:
        """P1 information units pass through byte-for-byte unchanged."""
        raw = "Deploy cluster-01 to region us-east-1. Please confirm status."
        messages = [{"role": "user", "content": raw}]
        unit = _make_unit(0, preservation_class=PreservationClass.P1_INFORMATION)
        ctx = _make_ctx(messages, _make_pmap(unit))

        res = TransformerStage().process(ctx)
        assert res.messages[0]["content"] == raw

    def test_structured_content_is_never_transformed(self) -> None:
        """Units with structural type CODE_PYTHON, JSON, etc. are never transformed."""
        code_raw = "def compute(x):\n    # Please calculate\n    return x * 2"
        messages = [{"role": "user", "content": code_raw}]
        unit = ContextUnit(
            message_index=0,
            role="user",
            structural_type=StructuralType.CODE_PYTHON,
            detection_certainty=DetectionCertainty.DETECTED,
            preservation_class=PreservationClass.P2_COMPRESSIBLE,
            eligibility=_make_eligibility(allow_compression=True),
        )
        ctx = _make_ctx(messages, _make_pmap(unit))

        res = TransformerStage().process(ctx)
        assert res.messages[0]["content"] == code_raw

    def test_p2_prose_eligible_is_transformed(self) -> None:
        """P2 PROSE units with compressible filler are transformed."""
        raw = "Could you please basically provide the summary? Thank you."
        messages = [{"role": "user", "content": raw}]
        unit = _make_unit(
            0,
            preservation_class=PreservationClass.P2_COMPRESSIBLE,
            allow_compression=True,
        )
        ctx = _make_ctx(messages, _make_pmap(unit))

        res = TransformerStage().process(ctx)
        assert res.messages[0]["content"] != raw
        assert "provide the summary" in res.messages[0]["content"]
        assert "could you please" not in res.messages[0]["content"].lower()
        assert "thank you" not in res.messages[0]["content"].lower()


class TestCP7BPESafety:
    """BPE safety: verify absence of blind token truncation."""

    def test_long_prose_is_never_tail_truncated(self) -> None:
        """Long prose message must not be sliced at an arbitrary token index."""
        raw = (
            "System telemetry audit log section 1: Normal operating parameters observed "
            "across cluster node-01 through node-20. "
            "CPU load average 22.4%, memory utilization 41.2%, network ingress 1.2 Gbps. "
            "All diagnostic checks passed for background worker threads. "
            "Periodic health probe returned status code 200 OK. "
            "Standard maintenance tasks executed without deviation from standard "
            "operating procedure.\n\n"
            "CRITICAL_ALERT_ASSERTION: Node-99 entered fatal panic state with kernel error "
            "KERN-ERR-0x89AB. Immediate failover required."
        )
        messages = [{"role": "user", "content": raw}]
        invariants = (
            PreservedInvariant(
                category=EntityCategory.IDENTIFIER,
                invariant_type=InvariantType.LEXICAL,
                marker="KERN-ERR-0x89AB",
                message_index=0,
                role="user",
            ),
            PreservedInvariant(
                category=EntityCategory.SECURITY_COMPLIANCE,
                invariant_type=InvariantType.LEXICAL,
                marker="CRITICAL_ALERT_ASSERTION",
                message_index=0,
                role="user",
            ),
        )
        unit = _make_unit(
            0,
            preservation_class=PreservationClass.P2_COMPRESSIBLE,
            allow_compression=True,
            invariants=invariants,
        )
        ctx = _make_ctx(messages, _make_pmap(unit))

        res = TransformerStage().process(ctx)
        content = res.messages[0]["content"]
        # In CP5/CP6, BPE truncation sliced off the entire terminal alert.
        # In CP7, the terminal alert must be 100% intact!
        assert "KERN-ERR-0x89AB" in content
        assert "CRITICAL_ALERT_ASSERTION" in content
        assert "Immediate failover required." in content


class TestCP7Invariants:
    """Invariant preservation across multiple categories."""

    def test_all_invariant_categories_survive_transformation(self) -> None:
        """Identifiers, error codes, URLs, numeric constraints, and dates must survive."""
        raw = (
            "Please check node cluster-alpha-09 at https://acme.corp/api/v2. "
            "Encountered error code ERR-SEC-0x7F2A on 2026-03-31. "
            "Threshold limit is exactly 5000 requests. Thank you."
        )
        messages = [{"role": "user", "content": raw}]
        invariants = (
            PreservedInvariant(
                category=EntityCategory.IDENTIFIER,
                invariant_type=InvariantType.LEXICAL,
                marker="cluster-alpha-09",
                message_index=0,
                role="user",
            ),
            PreservedInvariant(
                category=EntityCategory.URL_OR_ENDPOINT,
                invariant_type=InvariantType.LEXICAL,
                marker="https://acme.corp/api/v2",
                message_index=0,
                role="user",
            ),
            PreservedInvariant(
                category=EntityCategory.ERROR_CODE,
                invariant_type=InvariantType.LEXICAL,
                marker="ERR-SEC-0x7F2A",
                message_index=0,
                role="user",
            ),
            PreservedInvariant(
                category=EntityCategory.DATETIME_CONSTRAINT,
                invariant_type=InvariantType.LEXICAL,
                marker="2026-03-31",
                message_index=0,
                role="user",
            ),
            PreservedInvariant(
                category=EntityCategory.NUMERIC_CONSTRAINT,
                invariant_type=InvariantType.LEXICAL,
                marker="5000 requests",
                message_index=0,
                role="user",
            ),
        )
        unit = _make_unit(
            0,
            preservation_class=PreservationClass.P2_COMPRESSIBLE,
            allow_compression=True,
            invariants=invariants,
        )
        ctx = _make_ctx(messages, _make_pmap(unit))

        res = TransformerStage().process(ctx)
        out = res.messages[0]["content"]

        for inv in invariants:
            assert inv.marker in out
        # Filler stripped, pleasantry removed
        assert "please" not in out.lower()
        assert "thank you" not in out.lower()


class TestCP7BoundaryDetection:
    """Conservative boundary detection: technical patterns do not trigger false sentence splits."""

    def test_decimals_versions_abbreviations_endpoints(self) -> None:
        """Verify decimals, versions, abbreviations, URLs, endpoints don't split sentences."""
        from tokenopt.pipeline.transformer import _split_sentences

        text = (
            "Load is 22.4% and ingress is 1.2 Gbps for version v4.2 and PostgreSQL 16.0.1. "
            "Refer to e.g. section 3.14 at https://example.com/api/v1 for contact "
            "support@acme.corp. Have a great day."
        )
        invariants = ["PostgreSQL 16.0.1", "support@acme.corp"]
        sentences = _split_sentences(text, invariants)

        # Should split into 3 logical sentences
        assert len(sentences) == 3
        assert "22.4%" in sentences[0][0]
        assert "1.2 Gbps" in sentences[0][0]
        assert "v4.2" in sentences[0][0]
        assert "PostgreSQL 16.0.1" in sentences[0][0]
        assert "e.g." in sentences[1][0]
        assert "3.14" in sentences[1][0]
        assert "https://example.com/api/v1" in sentences[1][0]
        assert "support@acme.corp" in sentences[1][0]
        assert "Have a great day." in sentences[2][0]


class TestCP7FillerAndDirectives:
    """Directive keyword protection and certified filler removal."""

    def test_directives_are_strictly_preserved(self) -> None:
        """Sentences containing directive keywords must never be pruned."""
        raw = (
            "You must ensure the deployment is verified before maintenance MW-01. "
            "Do not restart background services. "
            "Hope this helps."
        )
        messages = [{"role": "user", "content": raw}]
        unit = _make_unit(
            0,
            preservation_class=PreservationClass.P2_COMPRESSIBLE,
            allow_compression=True,
        )
        ctx = _make_ctx(messages, _make_pmap(unit))

        res = TransformerStage().process(ctx)
        out = res.messages[0]["content"]

        assert "You must ensure the deployment is verified before maintenance MW-01." in out
        assert "Do not restart background services." in out
        assert "Hope this helps." not in out

    def test_inline_filler_removal(self) -> None:
        """Inline conversational filler phrases are removed when word boundaries match."""
        raw = "As a matter of fact, basically we could you please inspect the service."
        messages = [{"role": "user", "content": raw}]
        unit = _make_unit(
            0,
            preservation_class=PreservationClass.P2_COMPRESSIBLE,
            allow_compression=True,
        )
        ctx = _make_ctx(messages, _make_pmap(unit))

        res = TransformerStage().process(ctx)
        out = res.messages[0]["content"]
        assert "inspect the service" in out
        assert "as a matter of fact" not in out.lower()
        assert "basically" not in out.lower()
        assert "could you" not in out.lower()
        assert "please" not in out.lower()


class TestCP7DuplicateSentences:
    """Exact duplicate sentence removal."""

    def test_exact_duplicate_sentences_removed(self) -> None:
        """Exact identical sentences are deduplicated, keeping the first."""
        raw = (
            "Reviewing system status now. "
            "Reviewing system status now. "
            "All checks completed successfully."
        )
        messages = [{"role": "user", "content": raw}]
        unit = _make_unit(
            0,
            preservation_class=PreservationClass.P2_COMPRESSIBLE,
            allow_compression=True,
        )
        ctx = _make_ctx(messages, _make_pmap(unit))

        res = TransformerStage().process(ctx)
        out = res.messages[0]["content"]
        assert out.count("Reviewing system status now.") == 1
        assert "All checks completed successfully." in out

    def test_duplicate_with_invariant_is_not_removed(self) -> None:
        """Duplicate sentences containing invariants must not be removed."""
        raw = (
            "Target cluster is cluster-omega-99. "
            "Target cluster is cluster-omega-99."
        )
        messages = [{"role": "user", "content": raw}]
        inv = PreservedInvariant(
            category=EntityCategory.IDENTIFIER,
            invariant_type=InvariantType.LEXICAL,
            marker="cluster-omega-99",
            message_index=0,
            role="user",
        )
        unit = _make_unit(
            0,
            preservation_class=PreservationClass.P2_COMPRESSIBLE,
            allow_compression=True,
            invariants=(inv,),
        )
        ctx = _make_ctx(messages, _make_pmap(unit))

        res = TransformerStage().process(ctx)
        out = res.messages[0]["content"]
        # Because it contains an invariant, it is not pruned
        assert out.count("cluster-omega-99") == 2


class TestCP7Fallback:
    """Local preflight fallback to original content."""

    def test_local_preflight_failure_falls_back_to_original(self) -> None:
        """If local preflight fails, the original message is returned unmodified."""
        raw = "Important alert: token AUTH-XYZ-123. Hope this helps."
        messages = [{"role": "user", "content": raw}]
        inv = PreservedInvariant(
            category=EntityCategory.IDENTIFIER,
            invariant_type=InvariantType.LEXICAL,
            marker="AUTH-XYZ-123",
            message_index=0,
            role="user",
        )
        unit = _make_unit(
            0,
            preservation_class=PreservationClass.P2_COMPRESSIBLE,
            allow_compression=True,
            invariants=(inv,),
        )
        ctx = _make_ctx(messages, _make_pmap(unit))

        stage = TransformerStage()
        # Mock preflight to fail artificially
        with patch.object(stage, "_local_preflight", return_value=False):
            res = stage.process(ctx)

        # Must fall back to raw content unchanged
        assert res.messages[0]["content"] == raw
        assert res.metrics.get("transform_fallback_count") == 1


class TestCP7EndToEndPipeline:
    """End-to-end pipeline test across the 12 evaluation cases."""

    def test_all_12_cases_pass_validator_with_zero_rollbacks(self) -> None:
        """Run all 12 cases through Analyzer -> Router -> Transformer -> Validator."""
        from evaluation.cases import get_cases
        from tokenopt.pipeline.analyzer import AnalyzerStage
        from tokenopt.pipeline.router import RouterStage
        from tokenopt.pipeline.validator import ValidatorStage

        cases = get_cases()
        config = TokenOptConfig()
        pipeline = OptimizationPipeline(
            stages=[
                AnalyzerStage(config),
                RouterStage(config),
                TransformerStage(config),
                ValidatorStage(config),
            ],
            config=config,
        )

        for case in cases:
            ctx = pipeline.run(case.messages, "gpt-4o")
            # Validator must ACCEPT every case
            assert ctx.metrics.get("validation_decision") == "accept", (
                f"Case {case.id} was rejected by Validator: "
                f"violations={ctx.metrics.get('validation_violations')}"
            )
            assert ctx.metrics.get("rollback_applied") is False, (
                f"Case {case.id} suffered unexpected rollback"
            )
            # Invariants checked must equal invariants passed
            checked = ctx.metrics.get("validation_invariants_checked", 0)
            passed = ctx.metrics.get("validation_invariants_passed", 0)
            assert checked == passed, f"Case {case.id} lost invariants: {passed}/{checked}"
