"""Embedding utilities for semantic caching and RAG optimization."""

from __future__ import annotations

import hashlib

import numpy as np

# Optional imports for sentence-transformers
try:
    from sentence_transformers import SentenceTransformer
    _HAS_ST = True
except ImportError:
    _HAS_ST = False
    SentenceTransformer = None  # type: ignore


class EmbeddingProvider:
    """Provides embeddings for semantic similarity."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", device: str | None = None):
        self.model_name = model_name
        self._model: SentenceTransformer | None = None
        self._device = device

    def _ensure_model(self) -> SentenceTransformer:
        if not _HAS_ST:
            raise ImportError(
                "sentence-transformers not installed. "
                "Install with: pip install tokenopt[semantic]"
            )
        if self._model is None:
            self._model = SentenceTransformer(self.model_name, device=self._device)
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        """Generate embeddings for a list of texts."""
        model = self._ensure_model()
        return model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)

    def embed_single(self, text: str) -> np.ndarray:
        """Generate embedding for a single text."""
        return self.embed([text])[0]

    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two normalized embeddings."""
        return float(np.dot(a, b))


def hash_text(text: str) -> str:
    """Generate deterministic hash for text."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class SimpleEmbeddingProvider:
    """Fallback embedding using simple hash-based similarity (no ML deps)."""

    def embed(self, texts: list[str]) -> np.ndarray:
        # Return hash-based pseudo-embeddings for exact matching only
        return np.array([[hash_text(t)[:8]] for t in texts], dtype=object)

    def embed_single(self, text: str) -> np.ndarray:
        return self.embed([text])[0]

    def similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        # Exact match only
        return 1.0 if a[0] == b[0] else 0.0


def get_embedding_provider(
    model_name: str = "all-MiniLM-L6-v2",
    device: str | None = None,
    fallback: bool = True
) -> EmbeddingProvider | SimpleEmbeddingProvider:
    """Get the best available embedding provider."""
    if _HAS_ST:
        try:
            return EmbeddingProvider(model_name, device)
        except Exception:
            if not fallback:
                raise
    return SimpleEmbeddingProvider()
