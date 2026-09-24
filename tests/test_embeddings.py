"""Tests for embedding utilities and fallback behavior."""

from __future__ import annotations

import numpy as np

from tokenopt.utils.embeddings import (
    EmbeddingProvider,
    SimpleEmbeddingProvider,
    get_embedding_provider,
    hash_text,
)


def test_hash_text_deterministic():
    """hash_text returns a 16-character deterministic hex string."""
    h1 = hash_text("hello world")
    h2 = hash_text("hello world")
    h3 = hash_text("goodbye world")

    assert len(h1) == 16
    assert h1 == h2
    assert h1 != h3


def test_simple_embedding_provider_exact_matching():
    """SimpleEmbeddingProvider implements exact-match pseudo-embeddings without ML dependencies."""
    provider = SimpleEmbeddingProvider()

    emb1 = provider.embed_single("query text")
    emb2 = provider.embed_single("query text")
    emb3 = provider.embed_single("different query text")

    assert isinstance(emb1, np.ndarray)
    assert provider.similarity(emb1, emb2) == 1.0
    assert provider.similarity(emb1, emb3) == 0.0


def test_simple_embedding_provider_batch():
    """SimpleEmbeddingProvider embeds multiple texts into a 2D array."""
    provider = SimpleEmbeddingProvider()
    texts = ["apple", "banana", "apple"]
    embs = provider.embed(texts)

    assert len(embs) == 3
    assert provider.similarity(embs[0], embs[2]) == 1.0
    assert provider.similarity(embs[0], embs[1]) == 0.0


def test_get_embedding_provider_fallback():
    """get_embedding_provider returns SimpleEmbeddingProvider or EmbeddingProvider safely."""
    provider = get_embedding_provider(fallback=True)
    assert isinstance(provider, (EmbeddingProvider, SimpleEmbeddingProvider))
    # It must support embed_single and similarity
    emb = provider.embed_single("test")
    assert provider.similarity(emb, emb) == 1.0
