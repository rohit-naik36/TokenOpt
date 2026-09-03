"""Unit tests for the semantic compressor (pure string logic, no deps)."""

from tokenopt_optimizer import SemanticCompressorV2


def test_filler_removal():
    c = SemanticCompressorV2()
    text = "This is basically a good idea, it is important to note that we proceed."
    result, techniques = c.compress(text)
    assert "basically" not in result
    assert "it is important to note that" not in result
    assert any(t.startswith("filler_removal") for t in techniques)


def test_connector_simplification():
    c = SemanticCompressorV2()
    text = "We did it in order to save time due to the fact that it matters."
    result, _ = c.compress(text)
    assert "in order to" not in result
    assert "due to the fact that" not in result
    assert "to save" in result
    assert "because it matters" in result


def test_whitespace_collapse():
    c = SemanticCompressorV2()
    result, _ = c.compress("Hello    world\n\n\n\nnext")
    assert "    " not in result
    assert "\n\n\n\n" not in result


def test_safe_compress_never_raises():
    c = SemanticCompressorV2()
    assert c.safe_compress("  a   b  ") == "a b"
    assert c.safe_compress("") == ""


def test_compress_idempotent_when_no_changes():
    c = SemanticCompressorV2()
    text = "plain text with no fillers"
    result, techniques = c.compress(text)
    assert result == text
    assert "semantic_compression" not in techniques
