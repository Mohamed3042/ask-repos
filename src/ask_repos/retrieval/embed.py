"""Local embeddings and reranking. No API key, no paid service, no network after warm-up.

`fastembed` runs ONNX models on the CPU. The two model ids are pinned in settings and
printed by `ask-repos corpus` so a reader can see exactly which weights produced the
vectors in the database.
"""

from __future__ import annotations

import hashlib
import math
import threading
from collections.abc import Iterable, Sequence
from typing import Protocol

from ask_repos.config import get_settings


class Embedder(Protocol):
    dim: int
    name: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    """The real embedder: `BAAI/bge-small-en-v1.5` (384 dims) by default."""

    def __init__(self, model_name: str | None = None, cache_dir: str | None = None) -> None:
        settings = get_settings()
        self.name = model_name or settings.embed_model
        self.dim = settings.embed_dim
        self._cache_dir = cache_dir or settings.model_cache_dir
        self._model = None
        self._lock = threading.Lock()

    def _ensure(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from fastembed import TextEmbedding

                    self._model = TextEmbedding(
                        model_name=self.name,
                        cache_dir=self._cache_dir,
                        enable_cpu_mem_arena=get_settings().onnx_cpu_mem_arena,
                    )
        return self._model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._ensure()
        return [vector.tolist() for vector in model.embed(list(texts))]

    def embed_query(self, text: str) -> list[float]:
        model = self._ensure()
        return next(iter(model.query_embed([text]))).tolist()


class HashEmbedder:
    """Deterministic, dependency-free stand-in used by tests that are not about model quality.

    It is a hashed bag of character trigrams, L2-normalised. It has no semantic power and
    is never selected at runtime - `get_embedder()` returns the real model unless a caller
    passes this in explicitly.
    """

    def __init__(self, dim: int | None = None) -> None:
        self.dim = dim or get_settings().embed_dim
        self.name = "hash-trigram (test only)"

    def _vector(self, text: str) -> list[float]:
        buckets = [0.0] * self.dim
        lowered = text.lower()
        for index in range(max(1, len(lowered) - 2)):
            gram = lowered[index : index + 3]
            digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
            buckets[int.from_bytes(digest[:4], "big") % self.dim] += 1.0
        norm = math.sqrt(sum(value * value for value in buckets)) or 1.0
        return [value / norm for value in buckets]

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class Reranker:
    """Local cross-encoder. Scores (query, passage) pairs; higher is better."""

    def __init__(
        self,
        model_name: str | None = None,
        cache_dir: str | None = None,
        batch_size: int | None = None,
    ) -> None:
        settings = get_settings()
        self.name = model_name or settings.rerank_model
        self._cache_dir = cache_dir or settings.model_cache_dir
        # Memory, not quality: a pair's score is the same whichever batch it lands in.
        self.batch_size = max(1, batch_size or settings.rerank_batch_size)
        self._model = None
        self._lock = threading.Lock()

    def _ensure(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from fastembed.rerank.cross_encoder import TextCrossEncoder

                    self._model = TextCrossEncoder(
                        model_name=self.name,
                        cache_dir=self._cache_dir,
                        enable_cpu_mem_arena=get_settings().onnx_cpu_mem_arena,
                    )
        return self._model

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        if not passages:
            return []
        scores = self._ensure().rerank(query, list(passages), batch_size=self.batch_size)
        return [float(score) for score in scores]


_embedder: Embedder | None = None
_reranker: Reranker | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = FastEmbedEmbedder()
    return _embedder


def get_reranker() -> Reranker:
    global _reranker
    if _reranker is None:
        _reranker = Reranker()
    return _reranker


def batched(items: Sequence[str], size: int = 64) -> Iterable[Sequence[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]
