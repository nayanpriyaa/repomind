"""Embedding abstraction.

The protocol keeps retrieval and ingestion free of any sentence-transformers
import, which is what makes those layers unit-testable without downloading a
model. The concrete encoder loads its weights on first use, never at import
time, and caches the instance for the process lifetime.
"""

from __future__ import annotations

import logging
import threading
from typing import Iterable, Protocol, Sequence, runtime_checkable

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_KNOWN_DIMENSIONS = {
    "sentence-transformers/all-MiniLM-L6-v2": 384,
    "all-MiniLM-L6-v2": 384,
    "sentence-transformers/all-mpnet-base-v2": 768,
    "BAAI/bge-small-en-v1.5": 384,
}


@runtime_checkable
class Embedder(Protocol):
    """Anything that can turn text into fixed-width float vectors."""

    @property
    def dimension(self) -> int:
        """Vector width produced by this embedder."""

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of indexable documents."""

    def embed_query(self, text: str) -> list[float]:
        """Embed a single search query."""


class SentenceTransformerEmbedder:
    """CPU-friendly encoder backed by ``sentence-transformers``.

    Loading is guarded by a lock so that concurrent FastAPI requests cannot
    trigger two simultaneous model loads on a cold process.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        batch_size: int = 32,
        device: str = "cpu",
        normalize: bool = True,
    ) -> None:
        self._model_name = model_name
        self._batch_size = max(1, batch_size)
        self._device = device
        self._normalize = normalize
        self._model: object | None = None
        self._dimension: int | None = _KNOWN_DIMENSIONS.get(model_name)
        self._lock = threading.Lock()

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def dimension(self) -> int:
        """Vector width, loading the model only if the size is not known."""
        if self._dimension is None:
            model = self._load()
            self._dimension = int(model.get_sentence_embedding_dimension())  # type: ignore[attr-defined]
        return self._dimension

    def _load(self):  # noqa: ANN202 - third-party type not imported at module level
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                logger.info("loading embedding model %s on %s", self._model_name, self._device)
                self._model = SentenceTransformer(self._model_name, device=self._device)
        return self._model

    def warm_up(self) -> None:
        """Eagerly load weights, e.g. during application startup."""
        self._load()

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        vectors = model.encode(  # type: ignore[attr-defined]
            list(texts),
            batch_size=self._batch_size,
            convert_to_numpy=True,
            normalize_embeddings=self._normalize,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class HashingEmbedder:
    """Deterministic dependency-free embedder.

    Not a semantic model: it maps token hashes into a fixed-width bag-of-words
    vector. It exists so the pipeline, the API and the evaluation harness can be
    exercised end to end in CI and in offline environments where downloading
    transformer weights is impossible. Never enable it in production.
    """

    def __init__(self, dimension: int = 384) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        import hashlib
        import math
        import re

        vector = [0.0] * self._dimension
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text.lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector


def build_embedder(model_name: str, batch_size: int = 32) -> Embedder:
    """Factory used by the container.

    ``EMBEDDING_MODEL=hashing`` selects the offline embedder; anything else is
    treated as a sentence-transformers model identifier.
    """
    if model_name.strip().lower() in {"hashing", "offline", "none"}:
        logger.warning("using HashingEmbedder - semantic quality will be poor")
        return HashingEmbedder()
    return SentenceTransformerEmbedder(model_name=model_name, batch_size=batch_size)


def iter_batches(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    """Yield fixed-size slices of ``items``."""
    step = max(1, size)
    for start in range(0, len(items), step):
        yield items[start : start + step]
