"""Tests for the SDK fidelity primitives."""

import asyncio

from tokenopt_optimizer import (
    DegradedFidelityValidator,
    FidelityScore,
    FidelityValidator,
)


def test_fidelity_score_holds_all_fields():
    s = FidelityScore(
        overall=0.9,
        semantic_similarity=0.85,
        structural_similarity=0.95,
        llm_judge_score=0.88,
        passed=True,
        details={"engine": "embedding"},
    )
    assert s.overall == 0.9
    assert s.semantic_similarity == 0.85
    assert s.structural_similarity == 0.95
    assert s.llm_judge_score == 0.88
    assert s.passed is True
    assert s.details == {"engine": "embedding"}


def test_fidelity_score_accepts_none_llm_judge():
    s = FidelityScore(
        overall=1.0,
        semantic_similarity=1.0,
        structural_similarity=1.0,
        llm_judge_score=None,
        passed=True,
        details={},
    )
    assert s.llm_judge_score is None


def test_degraded_validator_fails_open():
    v = DegradedFidelityValidator()
    score = asyncio.run(v.validate("orig", "opt"))
    assert score.passed is True
    assert score.overall == 1.0
    assert score.details["engine"] == "degraded_passthrough"


def test_degraded_validator_counts_validations():
    v = DegradedFidelityValidator()
    asyncio.run(v.validate("a", "b"))
    asyncio.run(v.validate("c", "d"))
    stats = v.get_stats()
    assert stats["engine"] == "degraded_passthrough"
    assert stats["validations"] == 2


def test_degraded_validator_starts_at_zero():
    v = DegradedFidelityValidator()
    assert v.get_stats()["validations"] == 0


def test_degraded_validator_is_runtime_match_for_protocol():
    assert isinstance(DegradedFidelityValidator(), FidelityValidator)


def test_fidelity_validator_protocol_is_runtime_checkable():
    assert getattr(FidelityValidator, "_is_runtime_protocol", False) or hasattr(
        FidelityValidator, "__instancecheck__"
    )
