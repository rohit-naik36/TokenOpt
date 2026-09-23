from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.base import OptimizationContext
from tokenopt.pipeline.rag_optimizer import RAGOptimizerStage


class _ZeroRelevanceProvider:
    def embed(self, texts):
        return list(texts)

    def embed_single(self, text):
        return text

    def similarity(self, a, b):
        return 0.0


def test_rag_does_not_rewrite_when_no_chunks_survive():
    config = TokenOptConfig(
        rag_similarity_threshold=0.5,
        rag_max_chunks=5,
    )

    original = (
        "Context:\n"
        "Customer ID ACME-84721\n"
        "Contract value USD 2,450,000\n"
        "Renewal date 2027-04-30\n"
        "Critical issue production deployment fails after API v3 migration\n"
        "Query: Explain the likely cause."
    )

    messages = [
        {"role": "user", "content": original},
    ]

    expected_messages = [
        message.copy()
        for message in messages
    ]

    ctx = OptimizationContext(
        messages=messages,
        model="gpt-4o",
        config=config,
    )

    stage = RAGOptimizerStage(config)
    stage._embedding_provider = _ZeroRelevanceProvider()

    result = stage.process(ctx)

    assert result.messages == expected_messages
    assert result.metrics["rag_original_chunks"] == 1
    assert result.metrics["rag_optimized_chunks"] == 0
    assert result.metrics["rag_optimization_applied"] is False