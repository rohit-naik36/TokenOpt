"""Test integration of Adaptive Compression into existing pipeline."""

import time

from tokenopt import OpenAI
from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.adaptive.contracts import Evaluator, FidelityResult
from tokenopt.pipeline.adaptive.stage import AdaptiveCompressorStage
from tokenopt.pipeline.base import OptimizationContext
from tokenopt.pipeline.compressor import CompressorStage


def _ctx(messages, model="gpt-4o", config=None):
    config = config or TokenOptConfig()
    return OptimizationContext(messages=messages, model=model, config=config)

class DeterministicTestEvaluator(Evaluator):
    """A deterministic evaluator for testing the feedback loop."""

    def __init__(self, reject_substrings=None, min_length_ratio=0.0):
        self.reject_substrings = reject_substrings or []
        self.min_length_ratio = min_length_ratio

    def evaluate(self, original: str, optimized: str) -> FidelityResult:
        # Reject if critical substrings are missing
        for req in self.reject_substrings:
            if req in original and req not in optimized:
                return FidelityResult(False, 0.0, 0.0, 0.0, {"missing": req}, False)

        # Reject if overly compressed
        if len(original) > 0 and len(optimized) / len(original) < self.min_length_ratio:
            return FidelityResult(False, 0.5, 0.5, 0.5, {"reason": "too short"}, False)

        return FidelityResult(True, 1.0, 1.0, 1.0, {}, False)

class SlowEvaluator(Evaluator):
    def evaluate(self, original: str, optimized: str) -> FidelityResult:
        time.sleep(1.1)
        return FidelityResult(False, 0.0, 0.0, 0.0, {}, False)


def test_adaptive_rejects_missing_content_and_retries():
    stage = AdaptiveCompressorStage()
    stage.evaluator = DeterministicTestEvaluator(min_length_ratio=0.8) # must keep 80% length

    text = (
        "Here is some conversational text that basically has a lot "
        "of fillers basically essentially "
    ) * 10

    ctx = _ctx([
        {"role": "user", "content": text},
        {"role": "user", "content": "I am the last query"}
    ])

    result = stage.process(ctx)
    assert result.metrics["compression_iterations"] > 0

def test_adaptive_preserves_mixed_prompt():
    stage = AdaptiveCompressorStage()
    stage.evaluator = DeterministicTestEvaluator()

    messages = [
        {"role": "system", "content": "You are a helpful assistant. Please basically explain."},
        {"role": "user", "content": "Historical filler conversation: please kindly ignore"},
        {"role": "user", "content": "RAG Chunk:\n{\n  \"fact\": \"sky is blue\"\n}"},
        {"role": "user", "content": "RAG Chunk:\n```python\nprint('code')\n```"},
        {
            "role": "user",
            "content": "please kindly basically explain this very simple concept "
            "to me right now"
        }
    ]

    ctx = _ctx(messages)
    result = stage.process(ctx)

    # System preserved
    assert result.messages[0]["content"] == "You are a helpful assistant. Please basically explain."

    # Filler conversation compressed
    assert len(result.messages[1]["content"]) <= len(messages[1]["content"])

    # JSON preserved
    assert "\"fact\": \"sky is blue\"" in result.messages[2]["content"]

    # Code preserved
    assert "```python\nprint('code')\n```" in result.messages[3]["content"]

    # Last user query preserved (this is a key adaptive feature vs legacy)
    assert "please kindly basically" in result.messages[4]["content"]

def test_adaptive_fails_open_on_exhausted_retries():
    stage = AdaptiveCompressorStage()
    # Require 99% length ratio, impossible with heuristic
    stage.evaluator = DeterministicTestEvaluator(min_length_ratio=0.99)

    text = "conversational filler please kindly basically" * 10
    ctx = _ctx([{"role": "user", "content": text}, {"role": "user", "content": "last query"}])

    result = stage.process(ctx)

    # Should exhaust retries and fail-open (return original text)
    assert result.messages[0]["content"] == text
    assert result.metrics["compression_iterations"] >= 2

def test_adaptive_fails_open_on_latency_budget():
    stage = AdaptiveCompressorStage()
    stage.evaluator = SlowEvaluator()

    text = "conversational filler please kindly basically" * 10
    ctx = _ctx([{"role": "user", "content": text}, {"role": "user", "content": "last query"}])

    result = stage.process(ctx)

    assert result.messages[0]["content"] == text
    assert result.metrics["compression_iterations"] > 2

def test_toggle_adaptive_false_uses_legacy():
    config = TokenOptConfig()
    config.enable_compression = True
    setattr(config, "enable_adaptive_compression", False)

    client = OpenAI(config=config, api_key="test_key")

    has_legacy = any(isinstance(s, CompressorStage) for s in client.pipeline.stages)
    has_adaptive = any(isinstance(s, AdaptiveCompressorStage) for s in client.pipeline.stages)

    assert has_legacy is True
    assert has_adaptive is False

def test_toggle_adaptive_true_uses_adaptive():
    config = TokenOptConfig()
    config.enable_compression = False
    setattr(config, "enable_adaptive_compression", True)

    client = OpenAI(config=config, api_key="test_key")

    has_legacy = any(isinstance(s, CompressorStage) for s in client.pipeline.stages)
    has_adaptive = any(isinstance(s, AdaptiveCompressorStage) for s in client.pipeline.stages)

    assert has_legacy is False
    assert has_adaptive is True
