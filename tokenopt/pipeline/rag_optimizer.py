"""RAG optimization stage for retrieval-augmented generation."""

from __future__ import annotations

from typing import Any

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.base import OptimizationContext, PipelineStage
from tokenopt.utils.embeddings import get_embedding_provider
from tokenopt.utils.messages import get_user_query


class RAGOptimizerStage(PipelineStage):
    """Optimize RAG chunks: deduplicate, rerank, filter by relevance."""

    name = "rag_optimizer"

    def __init__(self, config: TokenOptConfig | None = None):
        self.config = config or TokenOptConfig()
        self._embedding_provider = get_embedding_provider(fallback=True)

    def process(self, ctx: OptimizationContext) -> OptimizationContext:
        # Check if messages contain RAG context (typically in system or user messages)
        rag_chunks = self._extract_rag_chunks(ctx.messages)
        if not rag_chunks:
            return ctx

        # Get query for relevance scoring
        query = get_user_query(ctx.messages)
        if not query:
            return ctx

        # Optimize chunks
        optimized_chunks = self._optimize_chunks(rag_chunks, query)

        # Reconstruct messages with optimized chunks
        ctx.messages = self._reconstruct_messages(ctx.messages, optimized_chunks, query)
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
            scored.append((relevance, chunk, chunk_embeddings[i]))

        # Sort by relevance descending
        scored.sort(key=lambda x: -x[0])

        # Filter by threshold
        threshold = self.config.rag_similarity_threshold
        filtered = [(s, c, e) for s, c, e in scored if s >= threshold]

        # Deduplicate similar chunks
        deduplicated = self._deduplicate_chunks(
            [c for _, c, _ in filtered], [e for _, _, e in filtered]
        )

        # Limit to max chunks
        max_chunks = self.config.rag_max_chunks
        return deduplicated[:max_chunks]

    def _deduplicate_chunks(self, chunks: list[dict], embeddings: Any) -> list[dict]:
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

    def _reconstruct_messages(
        self,
        messages: list[dict],
        chunks: list[dict],
        query: str,
    ) -> list[dict]:
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
                new_content = f"Context:\n{chunk_text}\n\nQuery: {query}"
                new_messages.append({**msg, "content": new_content})
            else:
                new_messages.append(msg)

        return new_messages
