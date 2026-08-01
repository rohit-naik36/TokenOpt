"""Few-shot optimization stage."""

from __future__ import annotations

import random

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.base import OptimizationContext, PipelineStage
from tokenopt.utils.embeddings import get_embedding_provider
from tokenopt.utils.messages import get_user_query


class FewShotSelectorStage(PipelineStage):
    """Select optimal few-shot examples for the query."""

    name = "fewshot"

    def __init__(
        self,
        config: TokenOptConfig | None = None,
        examples: list[dict] | None = None,
    ):
        self.config = config or TokenOptConfig()
        self.examples = examples or []
        self._embedding_provider = get_embedding_provider(fallback=True)

    def process(self, ctx: OptimizationContext) -> OptimizationContext:
        if not self.examples:
            return ctx

        query = get_user_query(ctx.messages)
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

    def _select_examples(self, query: str) -> list[dict]:
        """Select few-shot examples based on strategy."""
        strategy = self.config.fewshot_selection_strategy
        max_examples = self.config.fewshot_max_examples

        if strategy == "similarity":
            return self._select_by_similarity(query, max_examples)
        elif strategy == "diversity":
            return self._select_by_diversity(query, max_examples)
        else:  # random
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
            best_score = -1.0

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
        example_pairs = []
        for ex in examples:
            if "input" in ex:
                example_pairs.append({"role": "user", "content": ex["input"]})
            if "output" in ex:
                example_pairs.append({"role": "assistant", "content": ex["output"]})

        new_messages = []
        fewshot_injected = False

        for msg in messages:
            new_messages.append(msg)
            if msg.get("role") == "system" and not fewshot_injected:
                # Inject after system message
                new_messages.extend(example_pairs)
                fewshot_injected = True

        if not fewshot_injected:
            new_messages = example_pairs + new_messages

        return new_messages
