import time
import pytest

from tokenopt.pipeline.adaptive.contracts import CompressionDecision, FidelityResult
from tokenopt.pipeline.adaptive.loop import AdaptiveCompressionLoop

class MockExecutor:
    def __init__(self, reduction_factor=0.5):
        self.reduction_factor = reduction_factor
        self.calls = []

    def execute(self, text: str, decision: CompressionDecision) -> str:
        self.calls.append(decision)
        if decision.target_technique == "whitespace_only":
            return text.strip()
        # Mock reduction based on aggressiveness
        target_len = int(len(text) * (1.0 - decision.aggressiveness_ratio))
        return text[:max(target_len, 1)]

class MockEvaluator:
    def __init__(self, pass_on_iteration=1):
        self.pass_on_iteration = pass_on_iteration
        self.calls = 0

    def evaluate(self, original: str, candidate: str) -> FidelityResult:
        self.calls += 1
        passed = self.calls >= self.pass_on_iteration
        return FidelityResult(
            passed=passed,
            overall_score=0.9 if passed else 0.5,
            semantic_similarity=0.9,
            structural_integrity=1.0
        )


def test_loop_bypasses_skip():
    executor = MockExecutor()
    evaluator = MockEvaluator()
    loop = AdaptiveCompressionLoop(executor, evaluator)

    decision = CompressionDecision(target_technique="skip", aggressiveness_ratio=0.0, target_tokens=100, retry_budget=0)
    result = loop.optimize_segment("hello world", decision)

    assert result.original_text == "hello world"
    assert result.optimized_text == "hello world"
    assert result.iterations == 0
    assert len(executor.calls) == 0


def test_loop_executes_whitespace_only():
    executor = MockExecutor()
    evaluator = MockEvaluator()
    loop = AdaptiveCompressionLoop(executor, evaluator)

    decision = CompressionDecision(target_technique="whitespace_only", aggressiveness_ratio=0.0, target_tokens=100, retry_budget=0)
    result = loop.optimize_segment("  hello world  ", decision)

    assert result.optimized_text == "hello world"
    assert result.iterations == 1


def test_loop_accepts_first_pass():
    executor = MockExecutor()
    evaluator = MockEvaluator(pass_on_iteration=1)
    loop = AdaptiveCompressionLoop(executor, evaluator, min_token_savings=5)

    # 20 chars long, 50% aggressiveness -> 10 chars -> 10 chars saved
    text = "a" * 20
    decision = CompressionDecision(target_technique="heuristic", aggressiveness_ratio=0.5, target_tokens=10, retry_budget=2)

    result = loop.optimize_segment(text, decision)
    assert result.iterations == 1
    assert result.tokens_saved == 10
    assert result.optimized_text == "a" * 10
    assert result.final_fidelity.passed is True


def test_loop_retries_and_lowers_aggressiveness():
    executor = MockExecutor()
    evaluator = MockEvaluator(pass_on_iteration=2) # fails first time, passes second
    loop = AdaptiveCompressionLoop(executor, evaluator, min_token_savings=1)

    text = "a" * 100
    decision = CompressionDecision(target_technique="ml_semantic", aggressiveness_ratio=0.8, target_tokens=20, retry_budget=2)

    result = loop.optimize_segment(text, decision)

    assert result.iterations == 2
    assert len(executor.calls) == 2
    # First call: 0.8
    assert executor.calls[0].aggressiveness_ratio == 0.8
    # Second call: 0.8 * 0.75 = 0.6
    assert round(executor.calls[1].aggressiveness_ratio, 2) == 0.6
    assert result.final_fidelity.passed is True


def test_loop_fails_open_if_budget_exhausted():
    executor = MockExecutor()
    evaluator = MockEvaluator(pass_on_iteration=99) # never passes
    loop = AdaptiveCompressionLoop(executor, evaluator)

    text = "a" * 100
    decision = CompressionDecision(target_technique="heuristic", aggressiveness_ratio=0.5, target_tokens=50, retry_budget=2)

    result = loop.optimize_segment(text, decision)

    assert result.optimized_text == text
    assert result.tokens_saved == 0
    assert len(executor.calls) == 3 # original + 2 retries
