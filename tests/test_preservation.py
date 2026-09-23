"""Unit tests for the PreservationMap data model and diagnostic types.

Verifies:
1. Enum values and string serialization.
2. Dataclass construction and type behavior.
3. Immutability / frozen behavior.
4. Default values.
5. Nested construction and querying helpers.
6. Optional character offsets behavior.
7. OptimizationContext integration.
"""

from dataclasses import FrozenInstanceError
import pytest

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.base import OptimizationContext, OptimizationPipeline
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


class TestPreservationEnums:
    """Test all preservation and classification enums."""

    def test_preservation_class_values(self):
        assert PreservationClass.P0_AUTHORITY == "P0"
        assert PreservationClass.P1_INFORMATION == "P1"
        assert PreservationClass.P2_COMPRESSIBLE == "P2"
        assert PreservationClass.P3_REMOVABLE == "P3"
        assert len(PreservationClass) == 4

    def test_invariant_type_values(self):
        assert InvariantType.LEXICAL == "lexical"
        assert InvariantType.SEMANTIC == "semantic"
        assert InvariantType.STRUCTURAL == "structural"
        assert len(InvariantType) == 3

    def test_structural_type_values(self):
        assert StructuralType.PROSE == "prose"
        assert StructuralType.CODE_PYTHON == "code_python"
        assert StructuralType.JSON == "json"
        assert StructuralType.MARKDOWN_TABLE == "markdown_table"
        assert StructuralType.TOOL_PAYLOAD == "tool_payload"
        assert len(StructuralType) == 5

    def test_detection_certainty_values(self):
        assert DetectionCertainty.DETECTED == "detected"
        assert DetectionCertainty.NOT_DETECTED == "not_detected"
        assert DetectionCertainty.AMBIGUOUS == "ambiguous"
        assert len(DetectionCertainty) == 3

    def test_entity_category_values(self):
        assert EntityCategory.IDENTIFIER == "identifier"
        assert EntityCategory.ERROR_CODE == "error_code"
        assert EntityCategory.URL_OR_ENDPOINT == "url_or_endpoint"
        assert EntityCategory.NUMERIC_CONSTRAINT == "numeric_constraint"
        assert EntityCategory.DATETIME_CONSTRAINT == "datetime_constraint"
        assert EntityCategory.NEGATIVE_CONSTRAINT == "negative_constraint"
        assert EntityCategory.CONFIGURATION_VALUE == "configuration_value"
        assert EntityCategory.SECURITY_COMPLIANCE == "security_compliance"
        assert len(EntityCategory) == 8


class TestPreservedInvariant:
    """Test PreservedInvariant dataclass."""

    def test_construction_and_attributes(self):
        inv = PreservedInvariant(
            category=EntityCategory.IDENTIFIER,
            invariant_type=InvariantType.LEXICAL,
            marker="service-auth",
            message_index=0,
            role="user",
            description="Service name identifier",
        )
        assert inv.category == EntityCategory.IDENTIFIER
        assert inv.invariant_type == InvariantType.LEXICAL
        assert inv.marker == "service-auth"
        assert inv.message_index == 0
        assert inv.role == "user"
        assert inv.description == "Service name identifier"

    def test_default_description(self):
        inv = PreservedInvariant(
            category=EntityCategory.ERROR_CODE,
            invariant_type=InvariantType.LEXICAL,
            marker="ERR-0x89AB",
            message_index=1,
            role="system",
        )
        assert inv.description == ""

    def test_immutability(self):
        inv = PreservedInvariant(
            category=EntityCategory.IDENTIFIER,
            invariant_type=InvariantType.LEXICAL,
            marker="service-auth",
            message_index=0,
            role="user",
        )
        with pytest.raises(FrozenInstanceError):
            inv.marker = "other-service"  # type: ignore

    def test_to_dict(self):
        inv = PreservedInvariant(
            category=EntityCategory.NUMERIC_CONSTRAINT,
            invariant_type=InvariantType.SEMANTIC,
            marker="150 words",
            message_index=2,
            role="user",
            description="Length constraint",
        )
        d = inv.to_dict()
        assert d == {
            "category": "numeric_constraint",
            "invariant_type": "semantic",
            "marker": "150 words",
            "message_index": 2,
            "role": "user",
            "description": "Length constraint",
        }


class TestTransformationEligibility:
    """Test TransformationEligibility dataclass."""

    def test_defaults(self):
        elig = TransformationEligibility()
        assert elig.allow_lossless_normalization is False
        assert elig.allow_meaning_preserving_compression is False
        assert elig.allow_removal is False
        assert elig.allow_truncation is False
        assert elig.required_validators == ()

    def test_custom_values_and_tuple_coercion(self):
        elig = TransformationEligibility(
            allow_lossless_normalization=True,
            allow_meaning_preserving_compression=True,
            allow_removal=True,
            allow_truncation=False,
            required_validators=["marker_validator", "json_validator"],  # type: ignore
        )
        assert elig.allow_lossless_normalization is True
        assert elig.allow_meaning_preserving_compression is True
        assert elig.allow_removal is True
        assert elig.allow_truncation is False
        assert isinstance(elig.required_validators, tuple)
        assert elig.required_validators == ("marker_validator", "json_validator")

    def test_immutability(self):
        elig = TransformationEligibility()
        with pytest.raises(FrozenInstanceError):
            elig.allow_truncation = True  # type: ignore

    def test_to_dict(self):
        elig = TransformationEligibility(
            allow_lossless_normalization=True,
            required_validators=("syntax_check",),
        )
        d = elig.to_dict()
        assert d == {
            "allow_lossless_normalization": True,
            "allow_meaning_preserving_compression": False,
            "allow_removal": False,
            "allow_truncation": False,
            "required_validators": ["syntax_check"],
        }


class TestContextUnit:
    """Test ContextUnit dataclass."""

    def test_construction_and_defaults(self):
        elig = TransformationEligibility(allow_lossless_normalization=True)
        unit = ContextUnit(
            message_index=0,
            role="user",
            structural_type=StructuralType.PROSE,
            detection_certainty=DetectionCertainty.DETECTED,
            preservation_class=PreservationClass.P2_COMPRESSIBLE,
            eligibility=elig,
        )
        assert unit.message_index == 0
        assert unit.role == "user"
        assert unit.structural_type == StructuralType.PROSE
        assert unit.detection_certainty == DetectionCertainty.DETECTED
        assert unit.preservation_class == PreservationClass.P2_COMPRESSIBLE
        assert unit.eligibility == elig
        assert unit.start_char is None
        assert unit.end_char is None
        assert unit.invariants == ()

    def test_optional_character_offsets(self):
        # Character offsets remain None for MVP, but the dataclass supports them
        # as future-facing optional ints without error.
        unit = ContextUnit(
            message_index=1,
            role="assistant",
            structural_type=StructuralType.CODE_PYTHON,
            detection_certainty=DetectionCertainty.DETECTED,
            preservation_class=PreservationClass.P1_INFORMATION,
            eligibility=TransformationEligibility(),
            start_char=10,
            end_char=150,
        )
        assert unit.start_char == 10
        assert unit.end_char == 150

    def test_invariants_tuple_coercion(self):
        inv = PreservedInvariant(
            category=EntityCategory.IDENTIFIER,
            invariant_type=InvariantType.LEXICAL,
            marker="DOC-101",
            message_index=0,
            role="user",
        )
        unit = ContextUnit(
            message_index=0,
            role="user",
            structural_type=StructuralType.PROSE,
            detection_certainty=DetectionCertainty.DETECTED,
            preservation_class=PreservationClass.P1_INFORMATION,
            eligibility=TransformationEligibility(),
            invariants=[inv],  # type: ignore
        )
        assert isinstance(unit.invariants, tuple)
        assert unit.invariants == (inv,)

    def test_immutability(self):
        unit = ContextUnit(
            message_index=0,
            role="user",
            structural_type=StructuralType.PROSE,
            detection_certainty=DetectionCertainty.DETECTED,
            preservation_class=PreservationClass.P1_INFORMATION,
            eligibility=TransformationEligibility(),
        )
        with pytest.raises(FrozenInstanceError):
            unit.preservation_class = PreservationClass.P3_REMOVABLE  # type: ignore

    def test_to_dict(self):
        inv = PreservedInvariant(
            category=EntityCategory.IDENTIFIER,
            invariant_type=InvariantType.LEXICAL,
            marker="DOC-101",
            message_index=0,
            role="user",
        )
        unit = ContextUnit(
            message_index=0,
            role="user",
            structural_type=StructuralType.PROSE,
            detection_certainty=DetectionCertainty.DETECTED,
            preservation_class=PreservationClass.P1_INFORMATION,
            eligibility=TransformationEligibility(),
            invariants=(inv,),
        )
        d = unit.to_dict()
        assert d["message_index"] == 0
        assert d["role"] == "user"
        assert d["structural_type"] == "prose"
        assert d["detection_certainty"] == "detected"
        assert d["preservation_class"] == "P1"
        assert d["start_char"] is None
        assert d["end_char"] is None
        assert d["invariants_count"] == 1
        assert len(d["invariants"]) == 1
        assert d["invariants"][0]["marker"] == "DOC-101"


class TestPreservationMap:
    """Test PreservationMap root dataclass and querying helpers."""

    def test_empty_map_defaults(self):
        pmap = PreservationMap()
        assert pmap.units == ()
        assert pmap.invariants == ()
        assert pmap.get_invariants_for_message(0) == []
        assert pmap.get_units_for_message(0) == []
        d = pmap.to_dict()
        assert d == {
            "invariants_count": 0,
            "units_count": 0,
            "invariants": [],
            "units": [],
        }

    def test_nested_construction_and_queries(self):
        inv0 = PreservedInvariant(
            category=EntityCategory.SECURITY_COMPLIANCE,
            invariant_type=InvariantType.LEXICAL,
            marker="JWT tokens",
            message_index=0,
            role="system",
            description="Auth requirement",
        )
        inv1_a = PreservedInvariant(
            category=EntityCategory.IDENTIFIER,
            invariant_type=InvariantType.LEXICAL,
            marker="service-billing",
            message_index=1,
            role="user",
        )
        inv1_b = PreservedInvariant(
            category=EntityCategory.NUMERIC_CONSTRAINT,
            invariant_type=InvariantType.SEMANTIC,
            marker="port 8443",
            message_index=1,
            role="user",
        )

        unit0 = ContextUnit(
            message_index=0,
            role="system",
            structural_type=StructuralType.PROSE,
            detection_certainty=DetectionCertainty.DETECTED,
            preservation_class=PreservationClass.P0_AUTHORITY,
            eligibility=TransformationEligibility(allow_lossless_normalization=True),
            invariants=(inv0,),
        )
        unit1 = ContextUnit(
            message_index=1,
            role="user",
            structural_type=StructuralType.PROSE,
            detection_certainty=DetectionCertainty.DETECTED,
            preservation_class=PreservationClass.P1_INFORMATION,
            eligibility=TransformationEligibility(),
            invariants=(inv1_a, inv1_b),
        )

        pmap = PreservationMap(
            units=[unit0, unit1],  # type: ignore
            invariants=[inv0, inv1_a, inv1_b],  # type: ignore
        )

        # Tuples coerced
        assert isinstance(pmap.units, tuple)
        assert isinstance(pmap.invariants, tuple)

        # Query helpers
        msg0_invs = pmap.get_invariants_for_message(0)
        assert len(msg0_invs) == 1
        assert msg0_invs[0].marker == "JWT tokens"

        msg1_invs = pmap.get_invariants_for_message(1)
        assert len(msg1_invs) == 2
        assert {inv.marker for inv in msg1_invs} == {"service-billing", "port 8443"}

        msg2_invs = pmap.get_invariants_for_message(2)
        assert msg2_invs == []

        msg0_units = pmap.get_units_for_message(0)
        assert len(msg0_units) == 1
        assert msg0_units[0].preservation_class == PreservationClass.P0_AUTHORITY

        msg1_units = pmap.get_units_for_message(1)
        assert len(msg1_units) == 1
        assert msg1_units[0].preservation_class == PreservationClass.P1_INFORMATION

        # Serialization
        d = pmap.to_dict()
        assert d["invariants_count"] == 3
        assert d["units_count"] == 2
        assert len(d["units"]) == 2
        assert len(d["invariants"]) == 3

    def test_immutability(self):
        pmap = PreservationMap()
        with pytest.raises(FrozenInstanceError):
            pmap.units = ()  # type: ignore


class TestOptimizationContextIntegration:
    """Test PreservationMap attachment to OptimizationContext."""

    def test_optimization_context_default_preservation_map_none(self):
        config = TokenOptConfig()
        ctx = OptimizationContext(
            messages=[{"role": "user", "content": "hello"}],
            model="gpt-4o",
            config=config,
        )
        assert ctx.preservation_map is None

    def test_optimization_context_with_preservation_map(self):
        config = TokenOptConfig()
        pmap = PreservationMap(
            units=(
                ContextUnit(
                    message_index=0,
                    role="user",
                    structural_type=StructuralType.PROSE,
                    detection_certainty=DetectionCertainty.DETECTED,
                    preservation_class=PreservationClass.P3_REMOVABLE,
                    eligibility=TransformationEligibility(allow_removal=True),
                ),
            )
        )
        ctx = OptimizationContext(
            messages=[{"role": "user", "content": "hello"}],
            model="gpt-4o",
            config=config,
            preservation_map=pmap,
        )
        assert ctx.preservation_map is pmap
        assert len(ctx.preservation_map.units) == 1
        assert ctx.preservation_map.units[0].preservation_class == PreservationClass.P3_REMOVABLE

    def test_pipeline_run_preserves_compatibility(self):
        config = TokenOptConfig(
            enable_routing=False,
            enable_compression=False,
            enable_summarization=False,
        )
        pipeline = OptimizationPipeline(stages=[], config=config)
        messages = [{"role": "user", "content": "test message"}]
        ctx = pipeline.run(messages, "gpt-4o")

        assert ctx.preservation_map is None
        assert ctx.messages == messages
