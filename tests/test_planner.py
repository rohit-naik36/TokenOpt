"""Unit tests for CandidatePlanner.

Tests:
1. P0 produces no transformation candidate (unconditionally protected).
2. P1 produces no transformation candidate (unconditionally protected).
3. P2 produces a COMPRESS candidate only when allow_meaning_preserving_compression=True.
4. P2 does not produce a candidate when the eligibility flag is false.
5. P3 produces a REMOVE candidate only when allow_removal=True.
6. P3 is protected if allow_removal=False.
7. Candidate ordering is deterministic and matches input unit order.
8. Protected units are explicitly represented and retain preservation class and reason.
9. Multiple units produce independently inspectable decisions.
10. Planner does not mutate PreservationMap.
11. Planner does not mutate ContextUnit.
12. Same PreservationMap produces identical CandidatePlan.
13. Empty PreservationMap works.
14. Mixed P0/P1/P2/P3 units are classified correctly.
15. Existing 12-case evaluation corpus can be analyzed into a plan without modifying
    corpus messages.
16. No candidate is created merely because a unit is short.
17. No candidate is created merely because a unit contains a number.
18. No candidate is created merely because a unit contains a keyword.
19. Eligibility flags override generic preservation-class assumptions where data model allows.
20. Critical safety test: P0, P1, P2, P3 distinctions are preserved without generic collapse.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from evaluation.cases import get_cases
from tokenopt.pipeline.analyzer import ContextAnalyzer
from tokenopt.pipeline.planner import (
    CandidatePlan,
    CandidatePlanner,
    CandidateType,
    ProtectedUnit,
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


def _make_unit(
    message_index: int = 0,
    role: str = "user",
    structural_type: StructuralType = StructuralType.PROSE,
    detection_certainty: DetectionCertainty = DetectionCertainty.DETECTED,
    preservation_class: PreservationClass = PreservationClass.P2_COMPRESSIBLE,
    allow_lossless_normalization: bool = False,
    allow_meaning_preserving_compression: bool = False,
    allow_removal: bool = False,
    allow_truncation: bool = False,
    invariants: tuple[PreservedInvariant, ...] = (),
) -> ContextUnit:
    """Helper to construct a ContextUnit with explicit parameters."""
    return ContextUnit(
        message_index=message_index,
        role=role,
        structural_type=structural_type,
        detection_certainty=detection_certainty,
        preservation_class=preservation_class,
        eligibility=TransformationEligibility(
            allow_lossless_normalization=allow_lossless_normalization,
            allow_meaning_preserving_compression=allow_meaning_preserving_compression,
            allow_removal=allow_removal,
            allow_truncation=allow_truncation,
            required_validators=(),
        ),
        start_char=None,
        end_char=None,
        invariants=invariants,
    )


class TestPreservationRules:
    """Test mandatory preservation rules for P0, P1, P2, and P3."""

    def test_p0_produces_no_transformation_candidate(self):
        """1. P0 is NEVER eligible for removal or lossy transformation and produces no candidate."""
        unit = _make_unit(
            message_index=0,
            role="system",
            preservation_class=PreservationClass.P0_AUTHORITY,
            # Even if misconfigured, P0 must NEVER be a candidate
            allow_meaning_preserving_compression=True,
            allow_removal=True,
        )
        pmap = PreservationMap(units=(unit,))
        planner = CandidatePlanner()
        plan = planner.plan(pmap)

        assert len(plan.candidates) == 0
        assert len(plan.protected_units) == 1
        assert plan.is_protected(0) is True

        protected = plan.protected_units[0]
        assert protected.preservation_class == PreservationClass.P0_AUTHORITY
        assert "P0_AUTHORITY" in protected.reason
        assert protected.unit is unit

    def test_p1_produces_no_transformation_candidate(self):
        """2. P1 is NEVER eligible for removal or lossy transformation and produces no candidate."""
        inv = PreservedInvariant(
            category=EntityCategory.IDENTIFIER,
            invariant_type=InvariantType.LEXICAL,
            marker="cluster-prod-01",
            message_index=0,
            role="user",
        )
        unit = _make_unit(
            message_index=0,
            role="user",
            preservation_class=PreservationClass.P1_INFORMATION,
            # Even if misconfigured, P1 must NEVER be a candidate
            allow_meaning_preserving_compression=True,
            allow_removal=True,
            invariants=(inv,),
        )
        pmap = PreservationMap(units=(unit,), invariants=(inv,))
        planner = CandidatePlanner()
        plan = planner.plan(pmap)

        assert len(plan.candidates) == 0
        assert len(plan.protected_units) == 1
        assert plan.is_protected(0) is True

        protected = plan.protected_units[0]
        assert protected.preservation_class == PreservationClass.P1_INFORMATION
        assert "P1_INFORMATION" in protected.reason
        assert protected.unit is unit

    def test_p2_produces_compress_candidate_only_when_eligible(self):
        """3. P2 produces a COMPRESS candidate only when
        allow_meaning_preserving_compression=True.
        """
        unit = _make_unit(
            message_index=0,
            role="user",
            preservation_class=PreservationClass.P2_COMPRESSIBLE,
            allow_meaning_preserving_compression=True,
            allow_removal=False,
        )
        pmap = PreservationMap(units=(unit,))
        planner = CandidatePlanner()
        plan = planner.plan(pmap)

        assert len(plan.candidates) == 1
        assert len(plan.protected_units) == 0
        assert len(plan.compression_candidates) == 1
        assert len(plan.removal_candidates) == 0

        candidate = plan.candidates[0]
        assert candidate.candidate_type == CandidateType.COMPRESS
        assert candidate.preservation_class == PreservationClass.P2_COMPRESSIBLE
        assert candidate.message_index == 0
        assert "P2_COMPRESSIBLE" in candidate.reason
        assert candidate.unit is unit

    def test_p2_does_not_produce_candidate_when_flag_false(self):
        """4. P2 does not produce a candidate when allow_meaning_preserving_compression=False."""
        unit = _make_unit(
            message_index=0,
            role="user",
            preservation_class=PreservationClass.P2_COMPRESSIBLE,
            allow_meaning_preserving_compression=False,
            allow_removal=False,
        )
        pmap = PreservationMap(units=(unit,))
        planner = CandidatePlanner()
        plan = planner.plan(pmap)

        assert len(plan.candidates) == 0
        assert len(plan.protected_units) == 1
        assert plan.is_protected(0) is True

        protected = plan.protected_units[0]
        assert protected.preservation_class == PreservationClass.P2_COMPRESSIBLE
        assert "disallowed" in protected.reason.lower()

    def test_p3_produces_remove_candidate_only_when_eligible(self):
        """5. P3 produces a REMOVE candidate only when allow_removal=True."""
        unit = _make_unit(
            message_index=0,
            role="user",
            preservation_class=PreservationClass.P3_REMOVABLE,
            allow_meaning_preserving_compression=True,
            allow_removal=True,
        )
        pmap = PreservationMap(units=(unit,))
        planner = CandidatePlanner()
        plan = planner.plan(pmap)

        assert len(plan.candidates) == 1
        assert len(plan.protected_units) == 0
        assert len(plan.removal_candidates) == 1
        assert len(plan.compression_candidates) == 0

        candidate = plan.candidates[0]
        assert candidate.candidate_type == CandidateType.REMOVE
        assert candidate.preservation_class == PreservationClass.P3_REMOVABLE
        assert candidate.message_index == 0
        assert "P3_REMOVABLE" in candidate.reason
        assert candidate.unit is unit

    def test_p3_is_protected_if_allow_removal_false(self):
        """6. P3 is protected if allow_removal=False."""
        unit = _make_unit(
            message_index=0,
            role="user",
            preservation_class=PreservationClass.P3_REMOVABLE,
            allow_meaning_preserving_compression=True,
            allow_removal=False,
        )
        pmap = PreservationMap(units=(unit,))
        planner = CandidatePlanner()
        plan = planner.plan(pmap)

        assert len(plan.candidates) == 0
        assert len(plan.protected_units) == 1
        assert plan.is_protected(0) is True

        protected = plan.protected_units[0]
        assert protected.preservation_class == PreservationClass.P3_REMOVABLE
        assert "disallowed" in protected.reason.lower()

    def test_lossless_normalization_boundary_does_not_emit_candidate_in_checkpoint_4(self):
        """P0/P1 units are not emitted as transformation candidates in Checkpoint 4.

        `allow_lossless_normalization` exists in the PreservationMap
        eligibility model for future transformation planning, but
        Checkpoint 4 only produces COMPRESS and REMOVE candidates.
        """
        # P0 with allow_lossless_normalization=True
        unit_p0 = _make_unit(
            message_index=0,
            role="system",
            preservation_class=PreservationClass.P0_AUTHORITY,
            allow_lossless_normalization=True,
            allow_meaning_preserving_compression=False,
            allow_removal=False,
        )
        # P1 with allow_lossless_normalization=True
        unit_p1 = _make_unit(
            message_index=1,
            role="user",
            preservation_class=PreservationClass.P1_INFORMATION,
            allow_lossless_normalization=True,
            allow_meaning_preserving_compression=False,
            allow_removal=False,
        )
        pmap = PreservationMap(units=(unit_p0, unit_p1))
        plan = CandidatePlanner().plan(pmap)

        # Both must be protected; no candidate emitted in Checkpoint 4
        assert len(plan.candidates) == 0
        assert len(plan.protected_units) == 2
        assert plan.is_protected(0) is True
        assert plan.is_protected(1) is True
        assert plan.protected_units[0].preservation_class == PreservationClass.P0_AUTHORITY
        assert plan.protected_units[1].preservation_class == PreservationClass.P1_INFORMATION


class TestDeterminismAndOrdering:
    """Test deterministic output, candidate ordering, and reproducibility."""

    def test_candidate_ordering_is_deterministic(self):
        """7. Candidate and protected unit ordering matches the input PreservationMap unit
        sequence.
        """
        u0 = _make_unit(0, "system", preservation_class=PreservationClass.P0_AUTHORITY)
        u1 = _make_unit(
            1, "user", preservation_class=PreservationClass.P3_REMOVABLE, allow_removal=True
        )
        u2 = _make_unit(
            2,
            "assistant",
            preservation_class=PreservationClass.P2_COMPRESSIBLE,
            allow_meaning_preserving_compression=True,
        )
        u3 = _make_unit(3, "user", preservation_class=PreservationClass.P1_INFORMATION)
        u4 = _make_unit(
            4, "user", preservation_class=PreservationClass.P3_REMOVABLE, allow_removal=True
        )

        pmap = PreservationMap(units=(u0, u1, u2, u3, u4))
        planner = CandidatePlanner()
        plan = planner.plan(pmap)

        # Candidates must be in order: u1 (idx 1), u2 (idx 2), u4 (idx 4)
        assert [c.message_index for c in plan.candidates] == [1, 2, 4]
        assert plan.candidates[0].candidate_type == CandidateType.REMOVE
        assert plan.candidates[1].candidate_type == CandidateType.COMPRESS
        assert plan.candidates[2].candidate_type == CandidateType.REMOVE

        # Protected units must be in order: u0 (idx 0), u3 (idx 3)
        assert [p.message_index for p in plan.protected_units] == [0, 3]

    def test_same_preservation_map_produces_identical_plan(self):
        """12. Identical PreservationMap produces identical CandidatePlan across repeated runs."""
        u0 = _make_unit(0, "system", preservation_class=PreservationClass.P0_AUTHORITY)
        u1 = _make_unit(
            1,
            "user",
            preservation_class=PreservationClass.P2_COMPRESSIBLE,
            allow_meaning_preserving_compression=True,
        )
        pmap = PreservationMap(units=(u0, u1))
        planner = CandidatePlanner()

        plan1 = planner.plan(pmap)
        plan2 = planner.plan(pmap)

        assert plan1 == plan2
        assert plan1.to_dict() == plan2.to_dict()


class TestProtectedRepresentation:
    """Test explicit protection representation and multi-unit inspection."""

    def test_protected_units_explicitly_represented(self):
        """8. Protected units are explicitly represented and retain detailed diagnostic metadata."""
        u_p0 = _make_unit(0, "system", preservation_class=PreservationClass.P0_AUTHORITY)
        u_p1_code = _make_unit(
            1,
            "user",
            structural_type=StructuralType.CODE_PYTHON,
            preservation_class=PreservationClass.P1_INFORMATION,
        )
        inv = PreservedInvariant(
            category=EntityCategory.ERROR_CODE,
            invariant_type=InvariantType.LEXICAL,
            marker="0x89AB",
            message_index=2,
            role="user",
        )
        u_p1_inv = _make_unit(
            2,
            "user",
            preservation_class=PreservationClass.P1_INFORMATION,
            invariants=(inv,),
        )

        pmap = PreservationMap(units=(u_p0, u_p1_code, u_p1_inv), invariants=(inv,))
        plan = CandidatePlanner().plan(pmap)

        assert len(plan.protected_units) == 3
        p0 = plan.get_protected_unit_for_message(0)
        p1 = plan.get_protected_unit_for_message(1)
        p2 = plan.get_protected_unit_for_message(2)

        assert p0 is not None and p0.preservation_class == PreservationClass.P0_AUTHORITY
        assert "authority" in p0.reason.lower()

        assert p1 is not None and p1.preservation_class == PreservationClass.P1_INFORMATION
        assert "code_python" in p1.reason

        assert p2 is not None and p2.preservation_class == PreservationClass.P1_INFORMATION
        assert "1 invariant(s)" in p2.reason

    def test_multiple_units_produce_independently_inspectable_decisions(self):
        """9. Multiple units produce independently inspectable decisions via helper methods."""
        u0 = _make_unit(0, "system", preservation_class=PreservationClass.P0_AUTHORITY)
        u1 = _make_unit(
            1, "user", preservation_class=PreservationClass.P3_REMOVABLE, allow_removal=True
        )
        u2 = _make_unit(
            2,
            "assistant",
            preservation_class=PreservationClass.P2_COMPRESSIBLE,
            allow_meaning_preserving_compression=True,
        )

        pmap = PreservationMap(units=(u0, u1, u2))
        plan = CandidatePlanner().plan(pmap)

        assert plan.is_protected(0) is True
        assert plan.is_protected(1) is False
        assert plan.is_protected(2) is False

        assert plan.get_protected_unit_for_message(0) is not None
        assert plan.get_candidate_for_message(1) is not None
        assert plan.get_candidate_for_message(1).candidate_type == CandidateType.REMOVE
        assert plan.get_candidate_for_message(2) is not None
        assert plan.get_candidate_for_message(2).candidate_type == CandidateType.COMPRESS


class TestImmutabilityAndSafety:
    """Test non-mutating behavior and boundary condition handling."""

    def test_planner_does_not_mutate_preservation_map(self):
        """10. Planner does not mutate the input PreservationMap."""
        u0 = _make_unit(0, "system", preservation_class=PreservationClass.P0_AUTHORITY)
        u1 = _make_unit(
            1,
            "user",
            preservation_class=PreservationClass.P2_COMPRESSIBLE,
            allow_meaning_preserving_compression=True,
        )
        pmap = PreservationMap(units=(u0, u1))
        pmap_snapshot = deepcopy(pmap)

        CandidatePlanner().plan(pmap)

        assert pmap == pmap_snapshot
        assert pmap.to_dict() == pmap_snapshot.to_dict()

    def test_planner_does_not_mutate_context_unit(self):
        """11. Planner does not mutate any ContextUnit."""
        u0 = _make_unit(
            0,
            "user",
            preservation_class=PreservationClass.P3_REMOVABLE,
            allow_removal=True,
        )
        u0_snapshot = deepcopy(u0)
        pmap = PreservationMap(units=(u0,))

        CandidatePlanner().plan(pmap)

        assert u0 == u0_snapshot
        assert u0.to_dict() == u0_snapshot.to_dict()

    def test_empty_preservation_map_works(self):
        """13. Empty PreservationMap produces an empty CandidatePlan without error."""
        pmap = PreservationMap(units=(), invariants=())
        plan = CandidatePlanner().plan(pmap)

        assert len(plan.candidates) == 0
        assert len(plan.protected_units) == 0
        assert len(plan.compression_candidates) == 0
        assert len(plan.removal_candidates) == 0
        assert plan.to_dict()["candidates_count"] == 0
        assert plan.to_dict()["protected_units_count"] == 0

    def test_none_preservation_map_raises_value_error(self):
        """Planner raises ValueError if preservation_map is None."""
        with pytest.raises(ValueError, match="preservation_map must not be None"):
            CandidatePlanner().plan(None)  # type: ignore[arg-type]

    def test_candidate_plan_accepts_lists_and_converts_to_tuples(self):
        """CandidatePlan converts list inputs to immutable tuples in __post_init__."""
        u0 = _make_unit(0, "system", preservation_class=PreservationClass.P0_AUTHORITY)
        prot = ProtectedUnit(
            unit=u0,
            message_index=0,
            preservation_class=PreservationClass.P0_AUTHORITY,
            reason="test",
        )
        plan = CandidatePlan(candidates=[], protected_units=[prot])
        assert isinstance(plan.candidates, tuple)
        assert isinstance(plan.protected_units, tuple)

    def test_lookups_return_none_when_message_index_not_found(self):
        """CandidatePlan lookup helpers return None when message index is not present."""
        plan = CandidatePlan()
        assert plan.get_candidate_for_message(999) is None
        assert plan.get_protected_unit_for_message(999) is None
        assert plan.is_protected(999) is False

    def test_planner_call_dunder_delegates_to_plan(self):
        """CandidatePlanner.__call__ delegates cleanly to plan()."""
        pmap = PreservationMap(units=(), invariants=())
        planner = CandidatePlanner()
        plan = planner(pmap)
        assert isinstance(plan, CandidatePlan)

    def test_unknown_preservation_class_defensive_fallback(self):
        """Unknown preservation classes are protected by the fail-safe policy."""
        unit = _make_unit(0, "user", preservation_class=PreservationClass.P2_COMPRESSIBLE)
        # Create a unit with a custom/unknown preservation_class value
        object.__setattr__(unit, "preservation_class", "UNKNOWN_FUTURE_CLASS")
        pmap = PreservationMap(units=(unit,))
        plan = CandidatePlanner().plan(pmap)

        assert len(plan.candidates) == 0
        assert len(plan.protected_units) == 1
        assert plan.is_protected(0) is True
        assert "UNKNOWN_CLASS" in plan.protected_units[0].reason



class TestHeuristicNonInterference:
    """Verify that decisions are strictly driven by preservation class and eligibility flags."""

    def test_no_candidate_created_merely_because_unit_is_short(self):
        """16. Short text is not made a candidate when classified as protected."""
        # e.g., "Stop." or "Deploy." in a P1 unit or P2 with compression disallowed
        unit_p1 = _make_unit(
            0,
            "user",
            preservation_class=PreservationClass.P1_INFORMATION,
            allow_removal=False,
            allow_meaning_preserving_compression=False,
        )
        plan = CandidatePlanner().plan(PreservationMap(units=(unit_p1,)))
        assert plan.is_protected(0) is True
        assert len(plan.candidates) == 0

    def test_no_candidate_created_merely_because_unit_contains_number(self):
        """17. Units containing numbers are not made candidates when marked P1."""
        inv = PreservedInvariant(
            category=EntityCategory.NUMERIC_CONSTRAINT,
            invariant_type=InvariantType.SEMANTIC,
            marker="150 words",
            message_index=0,
            role="user",
        )
        unit = _make_unit(
            0,
            "user",
            preservation_class=PreservationClass.P1_INFORMATION,
            invariants=(inv,),
        )
        plan = CandidatePlanner().plan(PreservationMap(units=(unit,), invariants=(inv,)))
        assert plan.is_protected(0) is True
        assert len(plan.candidates) == 0

    def test_no_candidate_created_merely_because_unit_contains_keyword(self):
        """18. Units containing pleasantry keywords are not candidates if classified P0 or P1."""
        unit_system_with_thanks = _make_unit(
            0,
            "system",
            preservation_class=PreservationClass.P0_AUTHORITY,
        )
        plan = CandidatePlanner().plan(PreservationMap(units=(unit_system_with_thanks,)))
        assert plan.is_protected(0) is True
        assert len(plan.candidates) == 0

    def test_eligibility_flags_override_generic_assumptions(self):
        """19. Explicit eligibility flags strictly govern candidate creation."""
        # P2 with compression disallowed -> protected
        p2_ineligible = _make_unit(
            0,
            "user",
            preservation_class=PreservationClass.P2_COMPRESSIBLE,
            allow_meaning_preserving_compression=False,
        )
        plan1 = CandidatePlanner().plan(PreservationMap(units=(p2_ineligible,)))
        assert plan1.is_protected(0) is True
        assert len(plan1.candidates) == 0

        # P3 with removal disallowed -> protected
        p3_ineligible = _make_unit(
            0,
            "user",
            preservation_class=PreservationClass.P3_REMOVABLE,
            allow_removal=False,
        )
        plan2 = CandidatePlanner().plan(PreservationMap(units=(p3_ineligible,)))
        assert plan2.is_protected(0) is True
        assert len(plan2.candidates) == 0


class TestCriticalSafety:
    """Test the mandatory multi-class preservation scenario."""

    def test_critical_safety_mixed_preservation_map(self):
        """20. Comprehensive verification that P0, P1, P2, P3 maintain distinct identities
        without generic collapse.
        """
        inv_num = PreservedInvariant(
            category=EntityCategory.NUMERIC_CONSTRAINT,
            invariant_type=InvariantType.SEMANTIC,
            marker="50,000 requests per minute",
            message_index=1,
            role="user",
        )
        inv_neg = PreservedInvariant(
            category=EntityCategory.NEGATIVE_CONSTRAINT,
            invariant_type=InvariantType.SEMANTIC,
            marker="do not restart",
            message_index=2,
            role="user",
        )

        u0_p0 = _make_unit(
            0,
            "system",
            preservation_class=PreservationClass.P0_AUTHORITY,
            allow_lossless_normalization=True,
            allow_meaning_preserving_compression=False,
            allow_removal=False,
        )
        u1_p1_num = _make_unit(
            1,
            "user",
            preservation_class=PreservationClass.P1_INFORMATION,
            invariants=(inv_num,),
            allow_meaning_preserving_compression=False,
            allow_removal=False,
        )
        u2_p1_neg = _make_unit(
            2,
            "user",
            preservation_class=PreservationClass.P1_INFORMATION,
            invariants=(inv_neg,),
            allow_meaning_preserving_compression=False,
            allow_removal=False,
        )
        u3_p2 = _make_unit(
            3,
            "user",
            preservation_class=PreservationClass.P2_COMPRESSIBLE,
            allow_meaning_preserving_compression=True,
            allow_removal=False,
        )
        u4_p3 = _make_unit(
            4,
            "user",
            preservation_class=PreservationClass.P3_REMOVABLE,
            allow_meaning_preserving_compression=True,
            allow_removal=True,
        )

        pmap = PreservationMap(
            units=(u0_p0, u1_p1_num, u2_p1_neg, u3_p2, u4_p3),
            invariants=(inv_num, inv_neg),
        )

        plan = CandidatePlanner().plan(pmap)

        # Must have exactly 2 candidates and 3 protected units
        assert len(plan.candidates) == 2
        assert len(plan.protected_units) == 3

        # 1. P0 is protected
        p0 = plan.get_protected_unit_for_message(0)
        assert p0 is not None
        assert p0.preservation_class == PreservationClass.P0_AUTHORITY
        assert "authority" in p0.reason.lower()

        # 2. P1 numeric is protected
        p1 = plan.get_protected_unit_for_message(1)
        assert p1 is not None
        assert p1.preservation_class == PreservationClass.P1_INFORMATION
        assert "P1_INFORMATION" in p1.reason

        # 3. P1 negative is protected
        p2 = plan.get_protected_unit_for_message(2)
        assert p2 is not None
        assert p2.preservation_class == PreservationClass.P1_INFORMATION
        assert "P1_INFORMATION" in p2.reason

        # 4. P2 is a compress candidate
        c3 = plan.get_candidate_for_message(3)
        assert c3 is not None
        assert c3.candidate_type == CandidateType.COMPRESS
        assert c3.preservation_class == PreservationClass.P2_COMPRESSIBLE
        assert "P2_COMPRESSIBLE" in c3.reason

        # 5. P3 is a remove candidate
        c4 = plan.get_candidate_for_message(4)
        assert c4 is not None
        assert c4.candidate_type == CandidateType.REMOVE
        assert c4.preservation_class == PreservationClass.P3_REMOVABLE
        assert "P3_REMOVABLE" in c4.reason


class TestCorpusIntegration:
    """Test candidate planning against the 12 evaluation corpus cases."""

    def test_all_12_cases_produce_valid_plans_without_mutating_corpus(self):
        """15. Existing 12-case evaluation corpus produces valid CandidatePlans without
        modifying corpus messages.
        """
        analyzer = ContextAnalyzer()
        planner = CandidatePlanner()
        cases = get_cases()

        assert len(cases) == 12

        for case in cases:
            messages_before = deepcopy(case.messages)

            pmap = analyzer.analyze(case.messages)
            plan = planner.plan(pmap)

            # Messages must NOT be modified
            assert case.messages == messages_before

            # Plan must be valid and cover all units
            total_decisions = len(plan.candidates) + len(plan.protected_units)
            assert total_decisions == len(case.messages)
            assert total_decisions == len(pmap.units)

            # Verify dictionary representation works
            d = plan.to_dict()
            assert d["candidates_count"] == len(plan.candidates)
            assert d["protected_units_count"] == len(plan.protected_units)
            assert d["compression_candidates_count"] == len(plan.compression_candidates)
            assert d["removal_candidates_count"] == len(plan.removal_candidates)
