"""Behavioral contract tests for the RAG optimizer stage."""

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.base import OptimizationContext
from tokenopt.pipeline.rag_optimizer import RAGOptimizerStage

CHUNK_A = ("alpha chunk content " * 8).strip()
CHUNK_B = ("bravo chunk content " * 8).strip()
CHUNK_C = ("charlie chunk content " * 8).strip()
CHUNK_D = ("delta chunk content " * 8).strip()
CHUNK_E = ("echo chunk content " * 8).strip()

QUERY = "what is the weather"


class _ScriptedProvider:
    """Embedding provider with scripted similarity for deterministic tests."""

    def __init__(self, sim_table):
        self._table = sim_table

    def embed(self, texts):
        return list(texts)

    def embed_single(self, text):
        return text

    def similarity(self, a, b):
        return self._table.get((a, b), self._table.get((b, a), 0.0))


def _ctx(config, context_content, query=QUERY):
    messages = [
        {"role": "user", "content": f"Context:\n{context_content}"},
        {"role": "user", "content": query},
    ]
    return OptimizationContext(messages=messages, model="gpt-4o", config=config)


def _stage(config):
    return RAGOptimizerStage(config)


def _all_relevant(chunks):
    table = {}
    for chunk in chunks:
        table[(QUERY, chunk)] = 0.99
    return table


def test_name():
    assert RAGOptimizerStage(TokenOptConfig()).name == "rag_optimizer"


def test_no_context_is_no_op():
    config = TokenOptConfig()
    messages = [{"role": "user", "content": "just a normal query"}]
    ctx = OptimizationContext(messages=messages, model="gpt-4o", config=config)
    result = _stage(config).process(ctx)
    assert result.messages == messages
    assert result.metrics == {}


def test_no_user_query_is_no_op():
    config = TokenOptConfig()
    messages = [{"role": "system", "content": f"Context:\n{CHUNK_A}"}]
    ctx = OptimizationContext(messages=messages, model="gpt-4o", config=config)
    result = _stage(config).process(ctx)
    assert result.messages == messages
    assert result.metrics == {}


def test_extraction_and_reconstruction():
    config = TokenOptConfig(rag_similarity_threshold=0.5, rag_max_chunks=5)
    stage = _stage(config)
    stage._embedding_provider = _ScriptedProvider(_all_relevant([CHUNK_A, CHUNK_B]))
    ctx = _ctx(config, f"{CHUNK_A}\n{CHUNK_B}")
    result = stage.process(ctx)
    assert result.metrics["rag_original_chunks"] == 2
    assert result.metrics["rag_optimized_chunks"] == 2
    assert result.metrics["rag_optimization_applied"] is True
    new_content = result.messages[0]["content"]
    assert new_content.startswith("Context:")
    assert CHUNK_A in new_content
    assert CHUNK_B in new_content
    assert f"Query: {QUERY}" in new_content
    assert result.messages[1] == {"role": "user", "content": QUERY}


def test_threshold_filters_low_relevance():
    config = TokenOptConfig(rag_similarity_threshold=0.5, rag_max_chunks=5)
    stage = _stage(config)
    stage._embedding_provider = _ScriptedProvider(
        {(QUERY, CHUNK_A): 0.6, (QUERY, CHUNK_B): 0.4}
    )
    ctx = _ctx(config, f"{CHUNK_A}\n{CHUNK_B}")
    result = stage.process(ctx)
    assert result.metrics["rag_optimized_chunks"] == 1
    assert CHUNK_A in result.messages[0]["content"]
    assert CHUNK_B not in result.messages[0]["content"]


def test_default_threshold_filters_mid_relevance():
    config = TokenOptConfig()
    stage = _stage(config)
    stage._embedding_provider = _ScriptedProvider(
        {(QUERY, CHUNK_A): 0.99, (QUERY, CHUNK_B): 0.6}
    )
    ctx = _ctx(config, f"{CHUNK_A}\n{CHUNK_B}")
    result = stage.process(ctx)
    assert result.metrics["rag_optimized_chunks"] == 1
    assert CHUNK_B not in result.messages[0]["content"]


def test_max_chunks_cap():
    config = TokenOptConfig(rag_similarity_threshold=0.5, rag_max_chunks=2)
    stage = _stage(config)
    chunks = [CHUNK_A, CHUNK_B, CHUNK_C, CHUNK_D, CHUNK_E]
    stage._embedding_provider = _ScriptedProvider(_all_relevant(chunks))
    ctx = _ctx(config, "\n".join(chunks))
    result = stage.process(ctx)
    assert result.metrics["rag_original_chunks"] == 5
    assert result.metrics["rag_optimized_chunks"] == 2


def test_dedup_removes_near_duplicates():
    config = TokenOptConfig(rag_similarity_threshold=0.5, rag_max_chunks=5)
    stage = _stage(config)
    stage._embedding_provider = _ScriptedProvider(
        {
            (QUERY, CHUNK_A): 0.99,
            (QUERY, CHUNK_B): 0.99,
            (CHUNK_A, CHUNK_B): 0.95,
        }
    )
    ctx = _ctx(config, f"{CHUNK_A}\n{CHUNK_B}")
    result = stage.process(ctx)
    assert result.metrics["rag_optimized_chunks"] == 1


def test_dedup_keeps_distinct_chunks():
    config = TokenOptConfig(rag_similarity_threshold=0.5, rag_max_chunks=5)
    stage = _stage(config)
    stage._embedding_provider = _ScriptedProvider(
        {
            (QUERY, CHUNK_A): 0.99,
            (QUERY, CHUNK_B): 0.99,
            (CHUNK_A, CHUNK_B): 0.5,
        }
    )
    ctx = _ctx(config, f"{CHUNK_A}\n{CHUNK_B}")
    result = stage.process(ctx)
    assert result.metrics["rag_optimized_chunks"] == 2


def test_dedup_uses_correct_embeddings_after_reorder():
    config = TokenOptConfig(rag_similarity_threshold=0.5, rag_max_chunks=5)
    stage = _stage(config)
    stage._embedding_provider = _ScriptedProvider(
        {
            (QUERY, CHUNK_A): 0.95,
            (QUERY, CHUNK_B): 0.98,
            (QUERY, CHUNK_C): 0.97,
            (CHUNK_A, CHUNK_A): 1.0,
            (CHUNK_B, CHUNK_B): 1.0,
            (CHUNK_C, CHUNK_C): 1.0,
            (CHUNK_A, CHUNK_B): 0.95,
            (CHUNK_A, CHUNK_C): 0.3,
            (CHUNK_B, CHUNK_C): 0.2,
        }
    )
    ctx = _ctx(config, f"{CHUNK_A}\n{CHUNK_B}\n{CHUNK_C}")
    result = stage.process(ctx)
    assert result.metrics["rag_optimized_chunks"] == 2
    content = result.messages[0]["content"]
    assert CHUNK_B in content
    assert CHUNK_C in content
    assert CHUNK_A not in content


def test_retrieved_keyword_extraction():
    config = TokenOptConfig(rag_similarity_threshold=0.5, rag_max_chunks=5)
    stage = _stage(config)
    stage._embedding_provider = _ScriptedProvider(_all_relevant([CHUNK_A]))
    messages = [
        {"role": "user", "content": f"Retrieved:\n{CHUNK_A}"},
        {"role": "user", "content": QUERY},
    ]
    ctx = OptimizationContext(messages=messages, model="gpt-4o", config=config)
    result = stage.process(ctx)
    assert result.metrics["rag_original_chunks"] == 1
    assert result.metrics["rag_optimization_applied"] is True


def test_structured_rag_chunks_key():
    config = TokenOptConfig(rag_similarity_threshold=0.5, rag_max_chunks=5)
    stage = _stage(config)
    stage._embedding_provider = _ScriptedProvider(_all_relevant([CHUNK_A]))
    messages = [
        {"role": "user", "content": QUERY, "rag_chunks": [{"text": CHUNK_A, "source": "doc"}]},
    ]
    ctx = OptimizationContext(messages=messages, model="gpt-4o", config=config)
    result = stage.process(ctx)
    assert result.metrics["rag_original_chunks"] == 1
    assert result.metrics["rag_optimized_chunks"] == 1


def test_malformed_content_skipped():
    config = TokenOptConfig()
    messages = [
        {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        {"role": "user", "content": QUERY},
    ]
    ctx = OptimizationContext(messages=messages, model="gpt-4o", config=config)
    result = _stage(config).process(ctx)
    assert result.messages == messages
    assert result.metrics == {}


def test_deterministic_for_identical_inputs():
    config = TokenOptConfig(rag_similarity_threshold=0.5, rag_max_chunks=5)
    stage = _stage(config)
    stage._embedding_provider = _ScriptedProvider(
        _all_relevant([CHUNK_A, CHUNK_B, CHUNK_C])
    )
    first = stage.process(_ctx(config, f"{CHUNK_A}\n{CHUNK_B}\n{CHUNK_C}"))
    second = stage.process(_ctx(config, f"{CHUNK_A}\n{CHUNK_B}\n{CHUNK_C}"))
    assert first.messages == second.messages
    assert first.metrics == second.metrics


def test_does_not_mutate_original_messages():
    config = TokenOptConfig(rag_similarity_threshold=0.5, rag_max_chunks=5)
    stage = _stage(config)
    stage._embedding_provider = _ScriptedProvider(_all_relevant([CHUNK_A, CHUNK_B]))
    ctx = _ctx(config, f"{CHUNK_A}\n{CHUNK_B}")
    expected = [m.copy() for m in ctx.original_messages]
    stage.process(ctx)
    assert ctx.original_messages == expected
