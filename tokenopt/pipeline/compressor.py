"""Prompt compression stage using heuristic and ML-based methods."""

from __future__ import annotations

import re
from typing import Any

from tokenopt.pipeline.base import OptimizationContext, PipelineStage
from tokenopt.utils.token_counter import count_message_tokens, count_tokens, truncate_to_tokens


class CompressorStage(PipelineStage):
    """Compress prompts while preserving semantic meaning."""

    name = "compressor"

    def __init__(self, config: Any = None):
        self.config = config
        self._llmlingua = None

    def _get_llmlingua(self):
        """Lazy-load LLMLingua if available."""
        if self._llmlingua is None:
            try:
                from llmlingua import PromptCompressor
                self._llmlingua = PromptCompressor()
            except ImportError:
                pass
        return self._llmlingua

    def process(self, ctx: OptimizationContext) -> OptimizationContext:
        target_tokens = int(ctx.original_token_count * ctx.config.compression_ratio)

        # Try ML-based compression first
        if self._get_llmlingua():
            ctx = self._compress_ml(ctx, target_tokens)
        else:
            ctx = self._compress_heuristic(ctx, target_tokens)

        ctx.metrics["compression_applied"] = True
        return ctx

    def _compress_ml(self, ctx: OptimizationContext, target_tokens: int) -> OptimizationContext:
        """Use LLMLingua for compression."""
        try:
            # Convert messages to single prompt
            prompt = self._messages_to_prompt(ctx.messages)
            compressed = self._llmlingua.compress_prompt(
                prompt,
                rate=ctx.config.compression_ratio,
                force_tokens=['.', '!', '?', '\n'],
            )
            # Convert back to messages format (simplified)
            ctx.messages = [{"role": "user", "content": compressed["compressed_prompt"]}]
        except Exception:
            # Fallback to heuristic
            ctx = self._compress_heuristic(ctx, target_tokens)
        return ctx

    def _compress_heuristic(
        self, ctx: OptimizationContext, target_tokens: int
    ) -> OptimizationContext:
        """Heuristic compression: remove redundancy, truncate."""
        compressed_messages = []

        for msg in ctx.messages:
            content = msg.get("content", "")
            if not isinstance(content, str):
                compressed_messages.append(msg)
                continue

            # Remove excessive whitespace
            content = re.sub(r'\n{3,}', '\n\n', content)
            content = re.sub(r' {2,}', ' ', content)

            # Remove common filler phrases
            filler_patterns = [
                r'\b(?:please|kindly|would you|could you)\b',
                r'\b(?:I think|I believe|in my opinion)\b',
                r'\b(?:basically|essentially|fundamentally)\b',
            ]
            for pattern in filler_patterns:
                content = re.sub(pattern, '', content, flags=re.IGNORECASE)

            # Truncate if still too long
            msg_tokens = count_tokens(content, ctx.model)
            if msg_tokens > target_tokens:
                content = truncate_to_tokens(content, target_tokens, ctx.model)

            compressed_messages.append({**msg, "content": content.strip()})

        ctx.messages = compressed_messages
        return ctx

    def _messages_to_prompt(self, messages: list[dict]) -> str:
        """Convert messages to single prompt string."""
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, str):
                parts.append(f"{role}: {content}")
        return "\n".join(parts)


class ContextSummarizerStage(PipelineStage):
    """Summarize conversation history to fit context window."""

    name = "summarizer"

    def __init__(self, summarizer_fn: callable = None):
        self.summarizer_fn = summarizer_fn

    def process(self, ctx: OptimizationContext) -> OptimizationContext:
        if len(ctx.messages) <= 2:
            return ctx

        token_count = count_message_tokens(ctx.messages, ctx.model)
        if token_count <= ctx.config.summarization_threshold:
            return ctx

        # Separate system message and recent messages
        system_msg = None
        recent_messages = []
        history_messages = []

        for msg in ctx.messages:
            if msg.get("role") == "system":
                system_msg = msg
            elif len(recent_messages) < 3:  # Keep last 3 messages
                recent_messages.insert(0, msg)
            else:
                history_messages.append(msg)

        if not history_messages:
            return ctx

        # Summarize history
        summary = self._summarize_history(history_messages, ctx.model)

        # Reconstruct messages
        new_messages = []
        if system_msg:
            new_messages.append(system_msg)
        new_messages.append(
            {"role": "system", "content": f"Previous conversation summary: {summary}"}
        )
        new_messages.extend(reversed(recent_messages))

        ctx.messages = new_messages
        ctx.metrics["summarization_applied"] = True
        ctx.metrics["summarized_messages"] = len(history_messages)
        return ctx

    def _summarize_history(self, messages: list[dict], model: str) -> str:
        """Generate summary of conversation history."""
        if self.summarizer_fn:
            return self.summarizer_fn(messages, model)

        # Simple extractive summary fallback
        user_messages = [
            m["content"]
            for m in messages
            if m.get("role") == "user" and isinstance(m.get("content"), str)
        ]
        if not user_messages:
            return "No user messages to summarize."

        # Take first and last user messages as summary
        summary_parts = []
        if user_messages:
            summary_parts.append(f"First query: {user_messages[0][:200]}")
        if len(user_messages) > 1:
            summary_parts.append(f"Last query: {user_messages[-1][:200]}")

        return " | ".join(summary_parts)
