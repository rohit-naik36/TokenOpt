import pytest

from tokenopt.pipeline.adaptive.analyzer import Analyzer
from tokenopt.pipeline.adaptive.contracts import CompressionProfile
from tokenopt.pipeline.adaptive.decider import Decider

def test_analyzer_identifies_code_blocks():
    analyzer = Analyzer()
    text = "Here is some code:\n```python\nprint('hello')\n```"
    profile = analyzer.analyze(text, role="user", segment_id="1")

    assert profile.risk_score == 1.0
    assert "CONTAINS_CODE" in profile.preservation_flags
    assert profile.signals["code_block"] == 1.0


def test_analyzer_identifies_system_prompt():
    analyzer = Analyzer()
    text = "You are a helpful assistant."
    profile = analyzer.analyze(text, role="system", segment_id="1")

    assert profile.risk_score == 1.0
    assert "IS_SYSTEM_PROMPT" in profile.preservation_flags
    assert profile.signals["positional"] == 1.0


def test_analyzer_identifies_structured_data():
    analyzer = Analyzer()
    text = '{"key": "value"}'
    profile = analyzer.analyze(text, role="user", segment_id="1")

    assert profile.risk_score == 1.0
    assert "CONTAINS_STRUCTURED_DATA" in profile.preservation_flags
    assert profile.signals["structural_data"] == 1.0


def test_analyzer_identifies_conversational_text():
    analyzer = Analyzer()
    text = "Please could you basically explain this to me? I think it is important."
    profile = analyzer.analyze(text, role="user", segment_id="1")

    assert profile.risk_score == 0.0
    assert not profile.preservation_flags
    assert profile.signals["conversational_fillers"] > 0
    assert profile.compressibility > 0.5


def test_decider_preserves_last_user_query():
    analyzer = Analyzer()
    decider = Decider()
    text = "What is the capital of France?"
    profile = analyzer.analyze(text, role="user", segment_id="1", is_last_user_query=True)
    decision = decider.decide(profile)

    assert decision.target_technique == "skip"
    assert decision.aggressiveness_ratio == 0.0
    assert decision.retry_budget == 0


def test_decider_preserves_code_but_allows_whitespace():
    analyzer = Analyzer()
    decider = Decider()
    text = "```\ncode\n```"
    profile = analyzer.analyze(text, role="user", segment_id="1")
    decision = decider.decide(profile)

    assert decision.target_technique == "whitespace_only"
    assert decision.aggressiveness_ratio == 0.0


def test_decider_highly_compressible_text():
    analyzer = Analyzer()
    decider = Decider()
    text = "Please could you basically explain this to me? I think it is important."
    profile = analyzer.analyze(text, role="user", segment_id="1")
    decision = decider.decide(profile)

    assert decision.target_technique == "ml_semantic"
    assert decision.aggressiveness_ratio == 0.6
    assert decision.retry_budget == 3
