"""Tests for the SDK semantic compressor."""

import pytest

import tokenopt_optimizer.compressor as comp_mod
from tokenopt_optimizer import SemanticCompressorV2


def test_filler_removal():
    c = SemanticCompressorV2()
    out, tech = c.compress("Please basically explain it to us")
    assert "basically" not in out
    assert any(t.startswith("filler_removal") for t in tech)


def test_filler_removal_counts_matches():
    c = SemanticCompressorV2()
    out, tech = c.compress("basically basically basically")
    remove = next(t for t in tech if t.startswith("filler_removal"))
    assert remove.endswith(":3")
    assert out.strip() == ""


def test_connector_replacement():
    c = SemanticCompressorV2()
    assert c.compress("in order to survive")[0] == "to survive"


def test_connector_replacement_due_to_the_fact_that():
    c = SemanticCompressorV2()
    assert c.compress("due to the fact that it rained")[0] == "because it rained"


def test_in_spite_and_event_and_daily():
    c = SemanticCompressorV2()
    assert c.compress("in spite of the fact that it snowed")[0] == "although it snowed"
    assert c.compress("we do it in the event that it helps")[0] == "we do it if it helps"
    assert c.compress("on a daily basis")[0] == "daily"


def test_whitespace_collapse_and_semantic_technique():
    c = SemanticCompressorV2()
    out, tech = c.compress("  hello    world   ")
    assert out == "hello world"
    assert "semantic_compression" in tech


def test_no_change_returns_original_without_semantic_technique():
    c = SemanticCompressorV2()
    out, tech = c.compress("hello world")
    assert out == "hello world"
    assert "semantic_compression" not in tech


def test_safe_compress_collapses_whitespace():
    c = SemanticCompressorV2()
    assert c.safe_compress("a   b\n\n\nc") == "a b\n\nc"


def test_safe_compress_strips_edges():
    c = SemanticCompressorV2()
    assert c.safe_compress("   leading   ") == "leading"


def test_safe_compress_noop_on_clean_text():
    c = SemanticCompressorV2()
    assert c.safe_compress("plain text") == "plain text"


def test_safe_compress_normalizes_punctuation_spacing():
    c = SemanticCompressorV2()
    assert c.safe_compress("hello , world .") == "hello, world."
    assert c.safe_compress("really ? yes !") == "really? yes!"


def test_safe_compress_collapses_excess_blank_lines():
    c = SemanticCompressorV2()
    assert c.safe_compress("a\n\n\n\n\nb") == "a\n\nb"


@pytest.mark.parametrize(
    "level,factor_low,factor_high",
    [
        ("aggressive", 0.0, 0.5),
        ("conservative", 0.5, 1.0),
        ("standard", 0.5, 0.5),
    ],
)
def test_headroom_ratio_tuning(monkeypatch, level, factor_low, factor_high):
    captured = {}

    class FakeResult:
        messages = [{"content": "compressed output"}]
        transforms_applied = ["smart_crusher"]
        tokens_before = 200
        tokens_after = 100
        tokens_saved = 100
        compression_ratio = 0.5

    def fake_headroom_compress(messages, model, config):
        captured["target_ratio"] = config.target_ratio
        return FakeResult()

    monkeypatch.setattr(comp_mod, "HEADROOM_AVAILABLE", True)
    monkeypatch.setattr(comp_mod, "headroom_compress", fake_headroom_compress)
    monkeypatch.setattr(comp_mod, "HeadroomConfig", lambda **kw: type("C", (), kw)())

    c = SemanticCompressorV2()
    text, techniques, stats = c.compress_with_headroom(
        "a " * 50, optimization_level=level, target_ratio=0.5
    )
    ratio = captured["target_ratio"]
    assert factor_low <= ratio <= factor_high
    assert text == "compressed output"
    assert techniques == ["headroom:smart_crusher"]
    assert stats["tokens_saved"] == 100


def test_headroom_fails_open_when_not_available(monkeypatch):
    monkeypatch.setattr(comp_mod, "HEADROOM_AVAILABLE", False)
    c = SemanticCompressorV2()
    text = "a fairly long prompt to test"
    compressed, techniques, stats = c.compress_with_headroom(text)
    assert compressed == text
    assert techniques == []
    assert stats == {}


def test_headroom_fails_open_when_no_messages(monkeypatch):
    class FakeResult:
        messages = []

    monkeypatch.setattr(comp_mod, "HEADROOM_AVAILABLE", True)
    monkeypatch.setattr(comp_mod, "headroom_compress", lambda *a, **k: FakeResult())

    c = SemanticCompressorV2()
    text, techniques, stats = c.compress_with_headroom("hello world")
    assert text == "hello world"
    assert techniques == []
    assert stats == {}


def test_headroom_fails_open_when_non_string_content(monkeypatch):
    class FakeResult:
        messages = [{"content": 123}]

    monkeypatch.setattr(comp_mod, "HEADROOM_AVAILABLE", True)
    monkeypatch.setattr(comp_mod, "headroom_compress", lambda *a, **k: FakeResult())

    c = SemanticCompressorV2()
    text, techniques, stats = c.compress_with_headroom("hello world")
    assert text == "hello world"
    assert techniques == []
    assert stats == {}


def test_headroom_fails_open_when_identical_text(monkeypatch):
    class FakeResult:
        messages = [{"content": "the same text"}]

    monkeypatch.setattr(comp_mod, "HEADROOM_AVAILABLE", True)
    monkeypatch.setattr(comp_mod, "headroom_compress", lambda *a, **k: FakeResult())

    c = SemanticCompressorV2()
    text, techniques, stats = c.compress_with_headroom("the same text")
    assert text == "the same text"
    assert techniques == []
    assert stats == {}


def test_headroom_fails_open_when_no_tokens_saved(monkeypatch):
    class FakeResult:
        messages = [{"content": "different"}]
        transforms_applied = ["smart_crusher"]
        tokens_saved = 0

    monkeypatch.setattr(comp_mod, "HEADROOM_AVAILABLE", True)
    monkeypatch.setattr(comp_mod, "headroom_compress", lambda *a, **k: FakeResult())

    c = SemanticCompressorV2()
    text, techniques, stats = c.compress_with_headroom("orig")
    assert text == "orig"
    assert techniques == []
    assert stats == {}


def test_headroom_fails_open_on_exception(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("headroom exploded")

    monkeypatch.setattr(comp_mod, "HEADROOM_AVAILABLE", True)
    monkeypatch.setattr(comp_mod, "headroom_compress", boom)

    c = SemanticCompressorV2()
    text, techniques, stats = c.compress_with_headroom("long input text")
    assert text == "long input text"
    assert techniques == []
    assert stats == {}


def test_headroom_uses_default_technique_when_no_transforms(monkeypatch):
    class FakeResult:
        messages = [{"content": "shortened"}]
        transforms_applied = None
        tokens_before = 200
        tokens_after = 100
        tokens_saved = 100
        compression_ratio = 0.5

    monkeypatch.setattr(comp_mod, "HEADROOM_AVAILABLE", True)
    monkeypatch.setattr(comp_mod, "headroom_compress", lambda *a, **k: FakeResult())

    c = SemanticCompressorV2()
    text, techniques, stats = c.compress_with_headroom("long enough input here")
    assert text == "shortened"
    assert techniques == ["headroom:smart_crusher"]


def test_compressor_patterns_are_word_boundaried():
    c = SemanticCompressorV2()
    # "actually" must not be stripped out of "actualized"
    out, _ = c.compress("I actually actualized the plan")
    assert "actualized" in out
    assert "actually" not in out
