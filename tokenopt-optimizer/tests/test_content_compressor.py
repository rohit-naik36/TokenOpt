"""Tests for ContentCompressor (tokenopt-optimizer)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from tokenopt_optimizer.content_compressor import (
    CompressorConfig,
    ContentCompressor,
    _fallback_compress,
    _headroom_compress,
    _sample_json_array,
)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _tool(content: str) -> dict:
    return {"role": "tool", "content": content}


def _assistant(content: str) -> dict:
    return {"role": "assistant", "content": content}


def _user(content: str) -> dict:
    return {"role": "user", "content": content}


def _enabled_cfg(**kw) -> CompressorConfig:
    return CompressorConfig(content_compression_enabled=True, **kw)


# ---------------------------------------------------------------------------
# Test 1: Stage disabled by default
# ---------------------------------------------------------------------------

class TestDisabled:
    def test_disabled_by_default(self) -> None:
        items = list(range(100))
        messages = [_tool(json.dumps(items))]
        cc = ContentCompressor()  # default: disabled
        result = cc.compress_messages(messages)

        assert result.messages[0]["content"] == json.dumps(items)
        assert result.backend == "disabled"
        assert result.messages_compressed == 0

    def test_disabled_config_explicit(self) -> None:
        cfg = CompressorConfig(content_compression_enabled=False)
        cc = ContentCompressor(cfg)
        messages = [_tool(json.dumps(list(range(50))))]
        result = cc.compress_messages(messages)
        assert result.messages_compressed == 0


# ---------------------------------------------------------------------------
# Test 2: Tool messages with large JSON arrays are compressed
# ---------------------------------------------------------------------------

class TestToolMessageCompression:
    def test_large_json_array_is_reduced(self) -> None:
        """Deterministic JSON-to-JSON fallback sampler reduces large arrays."""
        items = [{"id": i, "v": f"val{i}"} for i in range(50)]
        messages = [_tool(json.dumps(items))]
        cc = ContentCompressor(_enabled_cfg())
        cc._use_headroom = False
        result = cc.compress_messages(messages)

        compressed_items = json.loads(result.messages[0]["content"])
        assert len(compressed_items) < len(items)
        assert result.messages_compressed >= 1
        assert result.backend == "fallback"

    @pytest.mark.skipif(_headroom_compress is None, reason="headroom-ai is not installed")
    def test_large_json_array_headroom(self) -> None:
        """Headroom backend compresses large JSON arrays into tabular format."""
        items = [{"id": i, "v": f"val{i}"} for i in range(50)]
        raw = json.dumps(items)
        messages = [_tool(raw)]
        cc = ContentCompressor(_enabled_cfg())
        cc._use_headroom = True
        result = cc.compress_messages(messages)

        compressed = result.messages[0]["content"]
        assert compressed != raw
        assert len(compressed) < len(raw)
        assert result.messages_compressed >= 1
        assert result.backend == "headroom"

    def test_small_array_not_compressed(self) -> None:
        items = [{"x": i} for i in range(5)]
        messages = [_tool(json.dumps(items))]
        cc = ContentCompressor(_enabled_cfg())
        result = cc.compress_messages(messages)
        assert result.messages[0]["content"] == json.dumps(items)

    def test_plain_text_tool_message_unchanged(self) -> None:
        content = "process completed successfully"
        messages = [_tool(content)]
        cc = ContentCompressor(_enabled_cfg())
        result = cc.compress_messages(messages)
        assert result.messages[0]["content"] == content

    def test_object_json_tool_message_unchanged(self) -> None:
        content = json.dumps({"status": "ok", "count": 42})
        messages = [_tool(content)]
        cc = ContentCompressor(_enabled_cfg())
        result = cc.compress_messages(messages)
        assert result.messages[0]["content"] == content


# ---------------------------------------------------------------------------
# Test 3: User messages are never compressed
# ---------------------------------------------------------------------------

class TestUserMessagesSkipped:
    def test_user_message_with_large_array(self) -> None:
        items = list(range(100))
        messages = [_user(json.dumps(items))]
        cc = ContentCompressor(_enabled_cfg())
        result = cc.compress_messages(messages)
        assert result.messages[0]["content"] == json.dumps(items)
        assert result.messages_compressed == 0

    def test_user_messages_in_mixed_list(self) -> None:
        items = list(range(50))
        messages = [
            _user(json.dumps(items)),  # should NOT be compressed
            _tool(json.dumps(items)),  # should be compressed
        ]
        cc = ContentCompressor(_enabled_cfg())
        result = cc.compress_messages(messages)

        # User message unchanged
        assert result.messages[0]["content"] == json.dumps(items)
        # Tool message compressed
        assert result.messages_compressed == 1


# ---------------------------------------------------------------------------
# Test 4: Metrics (tokens_saved, backend label, messages_compressed)
# ---------------------------------------------------------------------------

class TestMetrics:
    def test_tokens_saved_non_negative(self) -> None:
        items = [{"id": i, "v": "x" * 30} for i in range(60)]
        messages = [_tool(json.dumps(items))]
        cc = ContentCompressor(_enabled_cfg())
        result = cc.compress_messages(messages)
        assert result.tokens_saved >= 0

    def test_backend_is_fallback_when_headroom_absent(self) -> None:
        items = [{"n": i} for i in range(50)]
        messages = [_tool(json.dumps(items))]
        with patch("tokenopt_optimizer.content_compressor._headroom_compress", None):
            cc = ContentCompressor(_enabled_cfg())
            cc._use_headroom = False
            result = cc.compress_messages(messages)
        assert result.backend == "fallback"

    def test_messages_compressed_count(self) -> None:
        items = list(range(50))
        messages = [_tool(json.dumps(items)), _tool(json.dumps(items))]
        cc = ContentCompressor(_enabled_cfg())
        result = cc.compress_messages(messages)
        assert result.messages_compressed == 2


# ---------------------------------------------------------------------------
# Test 5: Fail-open — exceptions do not propagate
# ---------------------------------------------------------------------------

class TestFailOpen:
    def test_headroom_exception_falls_back_silently(self) -> None:
        items = [{"id": i} for i in range(50)]
        content = json.dumps(items)
        messages = [_tool(content)]

        def _boom(text: str) -> str:
            raise RuntimeError("headroom exploded")

        with patch("tokenopt_optimizer.content_compressor._headroom_compress", _boom):
            cc = ContentCompressor(_enabled_cfg())
            cc._use_headroom = True
            result = cc.compress_messages(messages)  # must not raise

        # Output must still be a valid message
        assert result.messages[0]["role"] == "tool"

    def test_fallback_exception_passes_through(self) -> None:
        """If both headroom and fallback raise, original content is preserved."""
        content = json.dumps(list(range(50)))
        messages = [_tool(content)]

        with patch(
            "tokenopt_optimizer.content_compressor._fallback_compress",
            side_effect=RuntimeError("fallback exploded"),
        ):
            cc = ContentCompressor(_enabled_cfg())
            cc._use_headroom = False
            result = cc.compress_messages(messages)  # must not raise

        assert result.messages[0]["content"] == content


# ---------------------------------------------------------------------------
# Unit tests for pure-Python helpers
# ---------------------------------------------------------------------------

class TestSampleJsonArray:
    def test_keeps_head_and_tail_fractions(self) -> None:
        items = list(range(100))
        cfg = CompressorConfig(array_head_fraction=0.30, array_tail_fraction=0.15)
        result = _sample_json_array(items, cfg)
        assert result[0] == 0    # head kept
        assert result[-1] == 99  # tail kept
        assert len(result) < len(items)

    def test_deduplication_identical_rows(self) -> None:
        items = [{"x": 1}] * 50
        cfg = CompressorConfig()
        result = _sample_json_array(items, cfg)
        assert len(result) == 1

    def test_array_below_min_length_unchanged(self) -> None:
        items = [1, 2, 3]
        cfg = CompressorConfig(array_min_length=10)
        assert _sample_json_array(items, cfg) == items


class TestFallbackCompress:
    def test_prose_unchanged(self) -> None:
        cfg = CompressorConfig()
        assert _fallback_compress("Hello world", cfg) == "Hello world"

    def test_json_object_unchanged(self) -> None:
        cfg = CompressorConfig()
        content = '{"key": "val"}'
        assert _fallback_compress(content, cfg) == content

    def test_large_array_reduced(self) -> None:
        cfg = CompressorConfig()
        content = json.dumps(list(range(100)))
        result = _fallback_compress(content, cfg)
        parsed = json.loads(result)
        assert len(parsed) < 100

    def test_invalid_json_unchanged(self) -> None:
        cfg = CompressorConfig()
        content = "[not valid json"
        assert _fallback_compress(content, cfg) == content

    def test_result_is_valid_json(self) -> None:
        cfg = CompressorConfig()
        content = json.dumps([{"a": i, "b": "x" * 10} for i in range(50)])
        result = _fallback_compress(content, cfg)
        parsed = json.loads(result)
        assert isinstance(parsed, list)
