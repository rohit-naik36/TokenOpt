"""RAG optimization stage for retrieval-augmented generation."""

from __future__ import annotations

from typing import Any

from tokenopt.pipeline.base import OptimizationContext, PipelineStage
from tokenopt.utils.embeddings import get_embedding_provider


class RAGOptimizerStage(PipelineStage):
    """Optimize RAG chunks: deduplicate, rerank, filter by relevance."""

    name = "rag_optimizer"

    def __init__(self, config: Any = None):
        self.config = config
        self._embedding_provider = get_embedding_provider(fallback=True)

    def process(self, ctx: OptimizationContext) -> OptimizationContext:
        # Check if messages contain RAG context (typically in system or user messages)
        rag_chunks = self._extract_rag_chunks(ctx.messages)
        if not rag_chunks:
            return ctx

        # Get query for relevance scoring
        query = self._get_query(ctx.messages)
        if not query:
            return ctx

        # Optimize chunks
        optimized_chunks = self._optimize_chunks(rag_chunks, query)

        # Reconstruct messages with optimized chunks
        ctx.messages = self._reconstruct_messages(ctx.messages, optimized_chunks)
        ctx.metrics["rag_original_chunks"] = len(rag_chunks)
        ctx.metrics["rag_optimized_chunks"] = len(optimized_chunks)
        ctx.metrics["rag_optimization_applied"] = True

        return ctx

    def _extract_rag_chunks(self, messages: list[dict]) -> list[dict]:
        """Extract RAG chunks from messages. Looks for structured context."""
        chunks = []
        for msg in messages:
            content = msg.get("content", "")
            if not isinstance(content, str):
                continue

            # Look for common RAG patterns
            # Pattern: "Context:\n[chunk1]\n[chunk2]\n..." or similar
            if "context:" in content.lower() or "retrieved:" in content.lower():
                # Simple extraction - in practice, you'd parse your specific format
                lines = content.split("\n")
                for line in lines:
                    line = line.strip()
                    if line and len(line) > 50:  # Likely a chunk
                        chunks.append({"text": line, "source": "extracted"})

            # Also check for structured data in metadata
            if "rag_chunks" in msg:
                chunks.extend(msg["rag_chunks"])

        return chunks

    def _get_query(self, messages: list[dict]) -> str:
        """Extract query from messages."""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    return content
        return ""

    def _optimize_chunks(self, chunks: list[dict], query: str) -> list[dict]:
        """Deduplicate, rerank, and filter chunks."""
        if not chunks:
            return []

        # Embed chunks and query
        chunk_texts = [c.get("text", "") for c in chunks]
        query_embedding = self._embedding_provider.embed_single(query)
        chunk_embeddings = self._embedding_provider.embed(chunk_texts)

        # Score by relevance
        scored = []
        for i, chunk in enumerate(chunks):
            relevance = self._embedding_provider.similarity(query_embedding, chunk_embeddings[i])
            scored.append((relevance, chunk))

        # Sort by relevance descending
        scored.sort(key=lambda x: -x[0])

        # Filter by threshold
        threshold = self.config.rag_similarity_threshold
        filtered = [c for s, c in scored if s >= threshold]

        # Deduplicate similar chunks
        deduplicated = self._deduplicate_chunks(filtered, chunk_embeddings[:len(filtered)])

        # Limit to max chunks
        max_chunks = self.config.rag_max_chunks
        return deduplicated[:max_chunks]

    def _deduplicate_chunks(self, chunks: list[dict], embeddings) -> list[dict]:
        """Remove near-duplicate chunks."""
        if len(chunks) <= 1:
            return chunks

        unique = [chunks[0]]
        unique_embeddings = [embeddings[0]]

        for i, chunk in enumerate(chunks[1:], 1):
            is_duplicate = False
            for u_emb in unique_embeddings:
                sim = self._embedding_provider.similarity(embeddings[i], u_emb)
                if sim > 0.9:  # High similarity = duplicate
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique.append(chunk)
                unique_embeddings.append(embeddings[i])

        return unique

    def _reconstruct_messages(self, messages: list[dict], chunks: list[dict]) -> list[dict]:
        """Replace RAG context in messages with optimized chunks."""
        new_messages = []
        chunk_text = "\n".join([c.get("text", "") for c in chunks])

        for msg in messages:
            content = msg.get("content", "")
            if (
                isinstance(content, str)
                and ("context:" in content.lower() or "retrieved:" in content.lower())
            ):
                # Replace with optimized context
                new_content = f"Context:\n{chunk_text}\n\nQuery: {self._get_query(messages)}"
                new_messages.append({**msg, "content": new_content})
            else:
                new_messages.append(msg)

        return new_messages


class FewShotSelectorStage(PipelineStage):
    """Select optimal few-shot examples for the query."""

    name = "fewshot"

    def __init__(self, config: Any = None, examples: list[dict] = None):
        self.config = config
        self.examples = examples or []
        self._embedding_provider = get_embedding_provider(fallback=True)

    def process(self, ctx: OptimizationContext) -> OptimizationContext:
        if not self.examples:
            return ctx

        query = self._get_query(ctx.messages)
        if not query:
            return ctx

        # Select best examples
        selected = self._select_examples(query)

        # Inject as few-shot examples (prepend to messages after system)
        if selected:
            ctx.messages = self._inject_fewshot(ctx.messages, selected)
            ctx.metrics["fewshot_selected"] = len(selected)
            ctx.metrics["fewshot_applied"] = True

        return ctx

    def _get_query(self, messages: list[dict]) -> str:
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    return content
        return ""

    def _select_examples(self, query: str) -> list[dict]:
        """Select few-shot examples based on strategy."""
        strategy = self.config.fewshot_selection_strategy
        max_examples = self.config.fewshot_max_examples

        if strategy == "similarity":
            return self._select_by_similarity(query, max_examples)
        elif strategy == "diversity":
            return self._select_by_diversity(query, max_examples)
        else:  # random
            import random
            return random.sample(self.examples, min(max_examples, len(self.examples)))

    def _select_by_similarity(self, query: str, max_examples: int) -> list[dict]:
        """Select examples most similar to query."""
        query_emb = self._embedding_provider.embed_single(query)
        example_texts = [self._example_to_text(ex) for ex in self.examples]
        example_embs = self._embedding_provider.embed(example_texts)

        scored = []
        for i, ex in enumerate(self.examples):
            sim = self._embedding_provider.similarity(query_emb, example_embs[i])
            scored.append((sim, ex))

        scored.sort(key=lambda x: -x[0])
        return [ex for _, ex in scored[:max_examples]]

    def _select_by_diversity(self, query: str, max_examples: int) -> list[dict]:
        """Select diverse examples (maximal marginal relevance)."""
        # Simplified: pick first, then most dissimilar
        if not self.examples:
            return []

        selected = [self.examples[0]]
        remaining = self.examples[1:]

        while len(selected) < max_examples and remaining:
            best_idx = -1
            best_score = -1

            for i, ex in enumerate(remaining):
                # Score = similarity to query - max similarity to selected
                query_sim = self._embedding_provider.similarity(
                    self._embedding_provider.embed_single(query),
                    self._embedding_provider.embed_single(self._example_to_text(ex))
                )
                max_sel_sim = max(
                    self._embedding_provider.similarity(
                        self._embedding_provider.embed_single(self._example_to_text(sel)),
                        self._embedding_provider.embed_single(self._example_to_text(ex))
                    )
                    for sel in selected
                )
                score = query_sim - 0.5 * max_sel_sim
                if score > best_score:
                    best_score = score
                    best_idx = i

            if best_idx >= 0:
                selected.append(remaining.pop(best_idx))
            else:
                break

        return selected

    def _example_to_text(self, example: dict) -> str:
        """Convert example to text for embedding."""
        if "input" in example and "output" in example:
            return f"Input: {example['input']}\nOutput: {example['output']}"
        return str(example)

    def _inject_fewshot(self, messages: list[dict], examples: list[dict]) -> list[dict]:
        """Inject few-shot examples into messages."""
        new_messages = []
        fewshot_injected = False

        for msg in messages:
            new_messages.append(msg)
            if msg.get("role") == "system" and not fewshot_injected:
                # Inject after system message
                for ex in examples:
                    if "input" in ex:
                        new_messages.append({"role": "user", "content": ex["input"]})
                    if "output" in ex:
                        new_messages.append({"role": "assistant", "content": ex["output"]})
                fewshot_injected = True

        return new_messages
