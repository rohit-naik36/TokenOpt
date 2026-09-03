"""Unit tests for fidelity validation math and the degraded (fails-open) validator."""

import numpy as np
import pytest

import tokenopt_proxy_v2 as proxy
from fidelity_validator_v2 import EmbeddingFidelityValidator


def _math_validator():
    """Construct a validator without requiring an embedding backend.

    The _cosine_similarity and _structural_similarity methods are pure math
    helpers that do not touch the embedding backend, so we bypass __init__
    (which raises if no backend is configured).
    """
    return object.__new__(EmbeddingFidelityValidator)


def test_cosine_similarity_of_identical_vectors():
    v = _math_validator()
    a = np.array([1.0, 2.0, 3.0])
    b = np.array([1.0, 2.0, 3.0])
    assert v._cosine_similarity(a, b) == pytest.approx(1.0)


def test_cosine_similarity_of_orthogonal_vectors():
    v = _math_validator()
    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    assert v._cosine_similarity(a, b) == pytest.approx(0.0)


def test_cosine_similarity_zero_vector():
    v = _math_validator()
    assert v._cosine_similarity(np.array([0.0, 0.0]), np.array([1.0, 2.0])) == 0.0


def test_structural_similarity_perfect():
    v = _math_validator()
    assert v._structural_similarity("same text", "same text") == pytest.approx(1.0)


def test_structural_similarity_code_block_mismatch():
    v = _math_validator()
    score = v._structural_similarity("```python\nx=1\n```", "plain text")
    assert score < 1.0


def test_structural_similarity_json_mismatch():
    v = _math_validator()
    score = v._structural_similarity('{"a": 1}', "not json")
    assert score < 1.0


@pytest.mark.asyncio
async def test_degraded_validator_always_passes():
    validator = proxy.DegradedFidelityValidator()
    result = await validator.validate()
    assert result.passed is True
    assert result.overall == 1.0
    assert validator._validation_count == 1
