"""Tests for ContentCompressorStage."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.base import OptimizationContext
from tokenopt.pipeline.content_compressor import (
    _HEADROOM_AVAILABLE,
    ContentCompressorStage,
    _fallback_compress,
    _sample_json_array,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(messages: list[dict[str, Any]], enabled: bool = True) -> OptimizationContext:
    cfg = TokenOptConfig(content_compression_enabled=enabled)
    return OptimizationContext(messages=messages, model="gpt-4o-mini", config=cfg)


def _tool_msg(content: str) -> dict[str, Any]:
    return {"role": "tool", "content": content}


def _assistant_msg(content: str) -> dict[str, Any]:
    return {"role": "assistant", "content": content}


def _user_msg(content: str) -> dict[str, Any]:
    return {"role": "user", "content": content}


# ---------------------------------------------------------------------------
# Test 1: Stage is skipped when content_compression_enabled=False
# ---------------------------------------------------------------------------

class TestStageDisabled:
    def test_skipped_when_disabled(self) -> None:
        items = list(range(100))
        content = json.dumps(items)
        messages = [_tool_msg(content)]
        ctx = _make_ctx(messages, enabled=False)

        stage = ContentCompressorStage(ctx.config)
        result = stage.process(ctx)

        # Messages must be unchanged
        assert result.messages[0]["content"] == content
        assert result.metrics.get("content_compressor_skipped") == "disabled"
        assert "content_compressor_applied" not in result.metrics


# ---------------------------------------------------------------------------
# Test 2: Tool messages with large JSON arrays are compressed
# ---------------------------------------------------------------------------

class TestToolMessageCompression:
    def test_large_json_array_tool_message(self) -> None:
        """A tool message carrying a 50-item JSON array must be reduced via the fallback sampler.

        Explicitly forces _use_headroom = False to verify deterministic JSON-to-JSON
        fallback behavior independently of headroom availability.
        """
        items = [{"id": i, "value": f"v{i}"} for i in range(50)]
        content = json.dumps(items)
        messages = [_tool_msg(content)]
        ctx = _make_ctx(messages)

        stage = ContentCompressorStage(ctx.config)
        stage._use_headroom = False
        result = stage.process(ctx)

        compressed = result.messages[0]["content"]
        compressed_items = json.loads(compressed)

        assert len(compressed_items) < len(items), "Array should be shorter after compression"
        assert result.metrics["content_compressor_messages_compressed"] >= 1
        assert result.metrics["content_compressor_applied"] is True
        assert result.metrics["content_compressor_backend"] == "fallback"

    @pytest.mark.skipif(not _HEADROOM_AVAILABLE, reason="headroom-ai is not installed")
    def test_large_json_array_tool_message_headroom(self) -> None:
        """A tool message carrying a 50-item JSON array is compressed by headroom."""
        items = [{"id": i, "value": f"v{i}"} for i in range(50)]
        content = json.dumps(items)
        messages = [_tool_msg(content)]
        ctx = _make_ctx(messages)

        stage = ContentCompressorStage(ctx.config)
        stage._use_headroom = True
        result = stage.process(ctx)

        compressed = result.messages[0]["content"]
        assert compressed != content
        assert len(compressed) < len(content)
        assert result.metrics["content_compressor_messages_compressed"] >= 1
        assert result.metrics["content_compressor_applied"] is True
        assert result.metrics["content_compressor_backend"] == "headroom"
        assert result.metrics["content_compressor_headroom_effective"] is True
        assert 0 in result.metadata.get("content_format_changed", set())

    def test_small_json_array_passed_through(self) -> None:
        """Arrays with ≤ 10 items must not be modified."""
        items = [{"x": i} for i in range(5)]
        content = json.dumps(items)
        messages = [_tool_msg(content)]
        ctx = _make_ctx(messages)

        stage = ContentCompressorStage(ctx.config)
        result = stage.process(ctx)

        assert result.messages[0]["content"] == content

    def test_tool_message_non_json_passed_through(self) -> None:
        """Plain-text tool messages must pass through unchanged."""
        content = "OK: process finished successfully."
        messages = [_tool_msg(content)]
        ctx = _make_ctx(messages)

        stage = ContentCompressorStage(ctx.config)
        result = stage.process(ctx)

        assert result.messages[0]["content"] == content


# ---------------------------------------------------------------------------
# Test 3: User messages are never compressed
# ---------------------------------------------------------------------------

class TestUserMessageNotCompressed:
    def test_user_messages_skipped(self) -> None:
        items = list(range(100))
        content = json.dumps(items)
        messages = [_user_msg(content)]
        ctx = _make_ctx(messages)

        stage = ContentCompressorStage(ctx.config)
        result = stage.process(ctx)

        assert result.messages[0]["content"] == content
        assert result.metrics.get("content_compressor_messages_compressed", 0) == 0


# ---------------------------------------------------------------------------
# Test 4: Metrics are recorded correctly
# ---------------------------------------------------------------------------

class TestMetrics:
    def test_tokens_saved_metric(self) -> None:
        """tokens_saved should be non-negative when compression fires."""
        items = [{"id": i, "value": "x" * 20} for i in range(60)]
        content = json.dumps(items)
        messages = [_tool_msg(content)]
        ctx = _make_ctx(messages)

        stage = ContentCompressorStage(ctx.config)
        result = stage.process(ctx)

        assert result.metrics["content_compressor_tokens_saved"] >= 0
        assert "content_compressor_backend" in result.metrics

    def test_backend_label_is_fallback_when_headroom_absent(self) -> None:
        """Backend label must be 'fallback' when headroom is not importable."""
        items = [{"n": i} for i in range(50)]
        messages = [_tool_msg(json.dumps(items))]
        ctx = _make_ctx(messages)

        # Force fallback path regardless of real headroom availability.
        with patch(
            "tokenopt.pipeline.content_compressor._headroom_compress", None
        ):
            stage = ContentCompressorStage(ctx.config)
            stage._use_headroom = False
            result = stage.process(ctx)

        assert result.metrics["content_compressor_backend"] == "fallback"


# ---------------------------------------------------------------------------
# Test 5: Fail-open — exceptions in compress must not propagate
# ---------------------------------------------------------------------------

class TestFailOpen:
    def test_headroom_exception_falls_back_silently(self) -> None:
        """If headroom raises, stage falls back to Python compressor without raising."""
        items = [{"id": i} for i in range(50)]
        content = json.dumps(items)
        messages = [_tool_msg(content)]
        ctx = _make_ctx(messages)

        def _boom(text: str) -> str:
            raise RuntimeError("headroom exploded")

        with patch("tokenopt.pipeline.content_compressor._headroom_compress", _boom):
            stage = ContentCompressorStage(ctx.config)
            stage._use_headroom = True
            result = stage.process(ctx)  # must not raise

        # Result is either compressed by fallback or original; either is acceptable.
        assert result.messages[0]["role"] == "tool"
        assert result.metrics["content_compressor_applied"] is True

    def test_stage_level_exception_is_caught_by_pipeline(self) -> None:
        """OptimizationPipeline must restore messages if stage raises (existing behaviour)."""
        from tokenopt.pipeline.base import OptimizationPipeline

        items = [{"id": i} for i in range(50)]
        messages = [_tool_msg(json.dumps(items))]
        cfg = TokenOptConfig(
            content_compression_enabled=True,
            enable_compression=False,
            enable_routing=False,
            enable_summarization=False,
            cache_enabled=False,
            enable_rag=False,
            enable_fewshot=False,
        )

        class BrokenCompressor(ContentCompressorStage):
            def process(self, ctx: OptimizationContext) -> OptimizationContext:
                raise ValueError("intentional break")

        pipeline = OptimizationPipeline([BrokenCompressor(cfg)], cfg)
        result_ctx = pipeline.run(messages, "gpt-4o-mini")

        # Messages must be unchanged after pipeline restores checkpoint
        assert result_ctx.messages[0]["content"] == json.dumps(items)
        assert "content_compressor_error" in result_ctx.metrics


# ---------------------------------------------------------------------------
# Unit tests for pure-Python helpers
# ---------------------------------------------------------------------------

class TestSampleJsonArray:
    def test_keeps_head_and_tail(self) -> None:
        items = list(range(100))
        result = _sample_json_array(items)
        assert result[0] == 0         # head kept
        assert result[-1] == 99       # tail kept
        assert len(result) < len(items)

    def test_deduplication(self) -> None:
        items = [{"x": 1}] * 50
        result = _sample_json_array(items)
        assert len(result) == 1, "Identical rows should be deduplicated to one"

    def test_small_array_unchanged(self) -> None:
        items = [1, 2, 3]
        assert _sample_json_array(items) == items


class TestFallbackCompress:
    def test_non_array_json_unchanged(self) -> None:
        content = json.dumps({"key": "value"})
        assert _fallback_compress(content) == content

    def test_prose_unchanged(self) -> None:
        content = "Hello, this is plain text."
        assert _fallback_compress(content) == content

    def test_large_array_reduced(self) -> None:
        items = list(range(100))
        result = _fallback_compress(json.dumps(items))
        parsed = json.loads(result)
        assert len(parsed) < 100

    def test_invalid_json_unchanged(self) -> None:
        content = "[not valid json"
        assert _fallback_compress(content) == content


# ---------------------------------------------------------------------------
# Test 6: Backend Invariants
# ---------------------------------------------------------------------------

class TestBackendInvariants:
    @pytest.mark.skipif(not _HEADROOM_AVAILABLE, reason="headroom-ai is not installed")
    def test_headroom_compressible_input_never_returns_exact_unchanged_silently(self) -> None:
        """IF backend is 'headroom' and input is compressible, returning unchanged is failure."""
        items = [{"id": i, "value": f"v{i}"} for i in range(50)]
        content = json.dumps(items)
        messages = [_tool_msg(content)]
        ctx = _make_ctx(messages)

        stage = ContentCompressorStage(ctx.config)
        stage._use_headroom = True
        result = stage.process(ctx)

        compressed = result.messages[0]["content"]
        assert compressed != content, (
            "Headroom must not return exact unchanged content on compressible input"
        )
        assert len(compressed) < len(content), "Compressed content must be shorter than original"
        assert result.metrics["content_compressor_headroom_effective"] is True

    def test_headroom_passthrough_not_reported_as_headroom_effective(self) -> None:
        """If headroom fails or returns identical content, it fails open without claiming effect."""
        content = "Plain text that is not compressible by JSON or tabular format"
        messages = [_tool_msg(content)]
        ctx = _make_ctx(messages)

        stage = ContentCompressorStage(ctx.config)
        result = stage.process(ctx)

        # Content is unchanged, headroom_effective must be False
        assert result.messages[0]["content"] == content
        assert result.metrics.get("content_compressor_headroom_effective", False) is False
        assert result.metrics.get("content_compressor_messages_compressed", 0) == 0

    def test_headroom_failure_falls_back_without_reporting_headroom_effective(self) -> None:
        """If headroom raises, fallback path runs without claiming headroom effective."""
        items = [{"id": i, "value": f"v{i}"} for i in range(50)]
        content = json.dumps(items)
        messages = [_tool_msg(content)]
        ctx = _make_ctx(messages)

        def _raise_error(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("simulated headroom crash")

        with patch("tokenopt.pipeline.content_compressor._headroom_compress", _raise_error):
            stage = ContentCompressorStage(ctx.config)
            stage._use_headroom = True
            result = stage.process(ctx)

        # Fallback JSON sampler compressed it
        assert result.messages[0]["content"] != content
        assert result.metrics["content_compressor_headroom_effective"] is False
        assert result.metrics["content_compressor_messages_compressed"] == 1


# ---------------------------------------------------------------------------
# Test 7: Content Compression Roles
# ---------------------------------------------------------------------------

class TestContentCompressionRoles:
    def test_tool_messages_compressed_by_default(self) -> None:
        """By default, content_compression_roles is ['tool'] so tool messages are compressed."""
        items = [{"id": i, "value": f"v{i}"} for i in range(50)]
        content = json.dumps(items)
        messages = [_tool_msg(content)]
        ctx = _make_ctx(messages)

        stage = ContentCompressorStage(ctx.config)
        result = stage.process(ctx)

        assert result.messages[0]["content"] != content
        assert result.metrics["content_compressor_messages_compressed"] == 1

    def test_user_observation_compressed_when_enabled(self) -> None:
        """User message immediately following assistant is compressed with user-observation."""
        items = [{"id": i, "value": f"v{i}"} for i in range(50)]
        content = json.dumps(items)
        messages = [
            _user_msg("What are the items?"),
            _assistant_msg("Let me run a command to list them:"),
            _user_msg(content),  # user observation following assistant
        ]
        cfg = TokenOptConfig(
            content_compression_enabled=True,
            content_compression_roles=["tool", "user-observation"],
        )
        ctx = OptimizationContext(messages=messages, model="gpt-4o-mini", config=cfg)

        stage = ContentCompressorStage(cfg)
        result = stage.process(ctx)

        # Message 0: ordinary user prompt -> unchanged
        assert result.messages[0]["content"] == "What are the items?"
        # Message 1: assistant -> unchanged
        assert result.messages[1]["content"] == "Let me run a command to list them:"
        # Message 2: user-observation -> compressed!
        assert result.messages[2]["content"] != content
        assert len(result.messages[2]["content"]) < len(content)
        assert result.metrics["content_compressor_messages_compressed"] == 1
        assert 2 in result.metadata.get("content_format_changed", set())

    def test_ordinary_user_prompt_not_compressed_even_when_role_enabled(self) -> None:
        """Ordinary user prompts (not following an assistant message) are NOT compressed."""
        items = [{"id": i, "value": f"v{i}"} for i in range(50)]
        content = json.dumps(items)
        messages = [
            _user_msg(content),  # ordinary user prompt (first message, not after assistant)
        ]
        cfg = TokenOptConfig(
            content_compression_enabled=True,
            content_compression_roles=["tool", "user-observation"],
        )
        ctx = OptimizationContext(messages=messages, model="gpt-4o-mini", config=cfg)

        stage = ContentCompressorStage(cfg)
        result = stage.process(ctx)

        assert result.messages[0]["content"] == content
        assert result.metrics.get("content_compressor_messages_compressed", 0) == 0

    def test_user_observation_not_compressed_by_default(self) -> None:
        """User messages following assistant are NOT compressed under default roles (['tool'])."""
        items = [{"id": i, "value": f"v{i}"} for i in range(50)]
        content = json.dumps(items)
        messages = [
            _user_msg("List files"),
            _assistant_msg("Running ls:"),
            _user_msg(content),
        ]
        cfg = TokenOptConfig(
            content_compression_enabled=True,
            # default content_compression_roles = ["tool"]
        )
        ctx = OptimizationContext(messages=messages, model="gpt-4o-mini", config=cfg)

        stage = ContentCompressorStage(cfg)
        result = stage.process(ctx)

        assert result.messages[2]["content"] == content
        assert result.metrics.get("content_compressor_messages_compressed", 0) == 0


# ---------------------------------------------------------------------------
# Test 8: End-to-End Pipeline
# ---------------------------------------------------------------------------

class TestEndToEndPipeline:
    def test_e2e_analyzer_compressor_transformer_validator(self) -> None:
        """E2E integration test: Analyzer -> ContentCompressor -> Transformer -> Validator.

        Proves:
        1. Input contains compressible content (tool message with 50-item JSON array).
        2. ContentCompressor actually changes it.
        3. Transformer carries the changed content forward.
        4. Validator does not reject format change (syntax skipped for fmt_changed).
        5. Valid compression survives validation (ACCEPT, no rollback).
        6. Resulting optimized context is smaller.
        """
        from tokenopt.optimizer import CanonicalOptimizer

        items = [{"id": i, "service": f"svc_{i}", "status": "active"} for i in range(50)]
        content = json.dumps(items)
        messages = [
            {"role": "system", "content": "You are a helpful monitoring assistant."},
            {"role": "user", "content": "Check service health."},
            {"role": "assistant", "content": "Querying services..."},
            {"role": "tool", "content": content},
        ]

        cfg = TokenOptConfig(
            content_compression_enabled=True,
            enable_compression=True,
        )
        optimizer = CanonicalOptimizer(cfg)
        result = optimizer.optimize(messages, model="gpt-4o")

        assert result.validation_decision == "accept"
        assert result.rollback_applied is False
        tokens_saved = result.original_token_count - result.optimized_token_count
        assert tokens_saved > 0
        assert result.optimized_token_count < result.original_token_count
        # Message 3 (the tool message) was compressed
        assert result.optimized_messages[3]["content"] != content
        assert len(result.optimized_messages[3]["content"]) < len(content)

    def test_e2e_validator_still_rejects_genuinely_invalid_transformations(self) -> None:
        """Validator still catches and rejects genuine invariant violations."""
        from tokenopt.optimizer import CanonicalOptimizer
        from tokenopt.pipeline.validator import (
            InvariantViolation,
            ValidationDecision,
            ValidationResult,
            ValidatorStage,
        )

        items = [{"id": i, "code": f"ERR_{i}"} for i in range(50)]
        messages = [
            {"role": "system", "content": "Do not delete records under any circumstances."},
            {"role": "user", "content": "Check error logs."},
            {"role": "tool", "content": json.dumps(items)},
        ]

        cfg = TokenOptConfig(content_compression_enabled=True)
        optimizer = CanonicalOptimizer(cfg)

        with patch.object(
            ValidatorStage,
            "_validate",
            return_value=ValidationResult(
                passed=False,
                decision=ValidationDecision.REJECT,
                violations=(
                    InvariantViolation(
                        invariant_name="negative_constraint",
                        category="constraint",
                        invariant_type="preservation",
                        original_message_index=0,
                        role="system",
                        reason="Negative constraint violated",
                    ),
                ),
                checked_invariants_count=5,
                passed_invariants_count=4,
                failed_invariants_count=1,
            ),
        ):
            result = optimizer.optimize(messages, model="gpt-4o")
            assert result.validation_decision == "reject"
            assert result.rollback_applied is True
            assert result.original_token_count == result.optimized_token_count
            assert result.optimized_messages == messages

    @pytest.mark.skipif(not _HEADROOM_AVAILABLE, reason="headroom-ai is not installed")
    def test_e2e_user_observation_headroom_compression_to_validator_accept(self) -> None:
        """Integration test proving end-to-end user-observation Headroom compression:
        assistant msg -> user-observation payload -> ContentCompressor ->
        Headroom tabular output -> content_format_changed -> Validator -> ACCEPT.
        """
        from tokenopt.optimizer import CanonicalOptimizer

        items = [{"id": i, "name": f"user_{i}", "active": True} for i in range(50)]
        json_payload = json.dumps(items)
        user_prompt = "Please inspect all active customer records."
        messages = [
            {"role": "system", "content": "Database assistant. Never drop database tables."},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": "Executing SELECT * FROM customers;"},
            {"role": "user", "content": json_payload},
        ]

        cfg = TokenOptConfig(
            content_compression_enabled=True,
            content_compression_roles=["tool", "user-observation"],
            enable_compression=True,
        )
        optimizer = CanonicalOptimizer(cfg)
        result = optimizer.optimize(messages, model="gpt-4o")

        # 1. Pipeline outcome: full ACCEPT, no rollback
        assert result.validation_decision == "accept"
        assert result.rollback_applied is False

        # 2. Headroom actually changed message 3 (user-observation)
        obs_content = result.optimized_messages[3]["content"]
        assert obs_content != json_payload
        assert len(obs_content) < len(json_payload)
        # Headroom output is tabular (starts with [50]{...})
        assert obs_content.startswith('"[50]{') or obs_content.startswith("[50]{")

        # 3. user-observation targeting worked
        assert result.stage_metrics.get("content_compressor_messages_compressed") == 1
        assert result.stage_metrics.get("content_compressor_headroom_effective") is True

        # 4. Ordinary user prompt (message 1) is untouched by content compressor
        assert 1 not in result.stage_metrics.get("content_compressor_format_changed", [])

        # 5. format_changed is recorded for message 3
        assert result.stage_metrics.get("content_compressor_format_changed") == [3]

        # 6. Structural JSON validation was skipped for message 3:
        # obs_content is tabular text (NOT valid JSON list), yet validator accepted it
        import json as _json
        parsed = _json.loads(obs_content)
        assert not isinstance(parsed, list), "Headroom tabular string is not a JSON list"

        # 7. Other validator invariants remain active and passed
        assert result.validator_metrics.get("invariants_checked", 0) > 0
        assert result.validator_metrics.get("invariants_passed", 0) > 0
        assert result.validator_metrics.get("invariants_failed") == 0
        assert result.stage_metrics.get("validation_passed") is True

        # 8. Valid transformation survived validation and achieved savings
        assert result.original_token_count > result.optimized_token_count
        assert result.stage_metrics.get("content_compressor_tokens_saved", 0) > 0
