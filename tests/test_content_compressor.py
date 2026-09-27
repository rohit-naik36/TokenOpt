"""Tests for ContentCompressorStage."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.base import OptimizationContext
from tokenopt.pipeline.content_compressor import (
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
        """A tool message carrying a 50-item JSON array must be reduced."""
        items = [{"id": i, "value": f"v{i}"} for i in range(50)]
        content = json.dumps(items)
        messages = [_tool_msg(content)]
        ctx = _make_ctx(messages)

        stage = ContentCompressorStage(ctx.config)
        result = stage.process(ctx)

        compressed = result.messages[0]["content"]
        compressed_items = json.loads(compressed)

        assert len(compressed_items) < len(items), "Array should be shorter after compression"
        assert result.metrics["content_compressor_messages_compressed"] >= 1
        assert result.metrics["content_compressor_applied"] is True

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
