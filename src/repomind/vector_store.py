"""Vector-store abstraction.

The retrieval layer talks to this interface only. Qdrant's ``ScoredPoint`` and
filter objects never cross this boundary - :class:`qdrant_store.QdrantVectorStore`
translates them into :class:`VectorHit` values defined here. Swapping Qdrant for
another backend therefore touches exactly one module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Sequence

from .models import CodeChunk


@dataclass(frozen=True, slots=True)
class VectorRecord:
    """A vector plus the payload needed to render a citation without re-reading disk."""

    chunk_id: str
    vector: Sequence[float]
    payload: dict[str, Any]

    @classmethod
    def from_chunk(cls, chunk: CodeChunk, vector: Sequence[float]) -> "VectorRecord":
        return cls(chunk_id=chunk.chunk_id, vector=vector, payload=chunk.to_payload())


@dataclass(frozen=True, slots=True)
class VectorHit:
    """A similarity-search result, normalised across backends."""

    chunk_id: str
    score: float
    payload: dict[str, Any]


class VectorStore(ABC):
    """Minimal contract required by ingestion and retrieval."""

    @abstractmethod
    def ensure_collection(self, dimension: int) -> None:
        """Create the collection if it does not exist, validating dimensionality."""

    @abstractmethod
    def upsert(self, records: Sequence[VectorRecord]) -> int:
        """Insert or replace ``records``; returns how many were written."""

    @abstractmethod
    def search(
        self,
        vector: Sequence[float],
        top_k: int,
        repository_path: str | None = None,
    ) -> list[VectorHit]:
        """Return the ``top_k`` nearest neighbours, optionally repository-scoped."""

    @abstractmethod
    def delete_file(self, repository_path: str, file_path: str) -> None:
        """Remove every vector belonging to one file."""

    @abstractmethod
    def delete_repository(self, repository_path: str) -> None:
        """Remove every vector belonging to one repository."""

    @abstractmethod
    def count(self, repository_path: str | None = None) -> int:
        """Number of stored vectors, optionally repository-scoped."""

    @abstractmethod
    def health_check(self) -> bool:
        """Cheap liveness probe used by ``GET /ready``."""


class InMemoryVectorStore(VectorStore):
    """Exact brute-force store used by tests and offline evaluation runs."""

    def __init__(self) -> None:
        self._records: dict[str, VectorRecord] = {}
        self._dimension: int | None = None

    def ensure_collection(self, dimension: int) -> None:
        if self._dimension is not None and self._dimension != dimension:
            raise ValueError(
                f"collection dimension {self._dimension} != requested {dimension}"
            )
        self._dimension = dimension

    def upsert(self, records: Sequence[VectorRecord]) -> int:
        for record in records:
            self._records[record.chunk_id] = record
        return len(records)

    def search(
        self,
        vector: Sequence[float],
        top_k: int,
        repository_path: str | None = None,
    ) -> list[VectorHit]:
        hits = [
            VectorHit(
                chunk_id=record.chunk_id,
                score=_cosine(vector, record.vector),
                payload=record.payload,
            )
            for record in self._records.values()
            if repository_path is None
            or record.payload.get("repository_path") == repository_path
        ]
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:top_k]

    def delete_file(self, repository_path: str, file_path: str) -> None:
        for chunk_id, record in list(self._records.items()):
            payload = record.payload
            if (
                payload.get("repository_path") == repository_path
                and payload.get("file_path") == file_path
            ):
                del self._records[chunk_id]

    def delete_repository(self, repository_path: str) -> None:
        for chunk_id, record in list(self._records.items()):
            if record.payload.get("repository_path") == repository_path:
                del self._records[chunk_id]

    def count(self, repository_path: str | None = None) -> int:
        if repository_path is None:
            return len(self._records)
        return sum(
            1
            for record in self._records.values()
            if record.payload.get("repository_path") == repository_path
        )

    def health_check(self) -> bool:
        return True


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    import math

    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)
