"""Qdrant implementation of :class:`vector_store.VectorStore`.

Everything Qdrant-specific - the client, ``PointStruct``, ``Filter``,
``ScoredPoint`` - is confined to this module. The client itself is created lazily
so that importing the package (or running the unit test suite) does not require
``qdrant-client`` to be installed or a server to be reachable.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Sequence

from .vector_store import VectorHit, VectorRecord, VectorStore

logger = logging.getLogger(__name__)

_UPSERT_BATCH = 128


class QdrantVectorStore(VectorStore):
    """Vector storage and similarity search backed by a Qdrant server."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        collection: str = "repomind_chunks",
        timeout: float = 30.0,
        distance: str = "COSINE",
    ) -> None:
        self._host = host
        self._port = port
        self._collection = collection
        self._timeout = timeout
        self._distance = distance
        self._client: Any | None = None
        self._lock = threading.Lock()
        self._ensured_dimension: int | None = None

    @property
    def collection(self) -> str:
        return self._collection

    def _get_client(self) -> Any:
        """Create the Qdrant client on first use and reuse it thereafter."""
        if self._client is not None:
            return self._client
        with self._lock:
            if self._client is None:
                from qdrant_client import QdrantClient

                logger.info("connecting to qdrant at %s:%s", self._host, self._port)
                self._client = QdrantClient(
                    host=self._host, port=self._port, timeout=self._timeout
                )
        return self._client

    # -- schema ----------------------------------------------------------- #

    def ensure_collection(self, dimension: int) -> None:
        from qdrant_client import models as qmodels

        client = self._get_client()
        if client.collection_exists(self._collection):
            info = client.get_collection(self._collection)
            existing = _existing_dimension(info)
            if existing is not None and existing != dimension:
                raise ValueError(
                    f"collection {self._collection!r} has dimension {existing}, "
                    f"but the configured embedding model produces {dimension}. "
                    "Recreate the collection or change EMBEDDING_MODEL."
                )
        else:
            client.create_collection(
                collection_name=self._collection,
                vectors_config=qmodels.VectorParams(
                    size=dimension,
                    distance=qmodels.Distance[self._distance],
                ),
            )
            # Payload indexes keep repository/file filters from degrading into
            # full scans once several repositories share a collection.
            for field in ("repository_path", "file_path", "language", "chunk_type"):
                client.create_payload_index(
                    collection_name=self._collection,
                    field_name=field,
                    field_schema=qmodels.PayloadSchemaType.KEYWORD,
                )
        self._ensured_dimension = dimension

    # -- writes ----------------------------------------------------------- #

    def upsert(self, records: Sequence[VectorRecord]) -> int:
        if not records:
            return 0
        from qdrant_client import models as qmodels

        client = self._get_client()
        written = 0
        for start in range(0, len(records), _UPSERT_BATCH):
            batch = records[start : start + _UPSERT_BATCH]
            client.upsert(
                collection_name=self._collection,
                points=[
                    qmodels.PointStruct(
                        id=record.chunk_id,
                        vector=list(record.vector),
                        payload=record.payload,
                    )
                    for record in batch
                ],
                wait=True,
            )
            written += len(batch)
        return written

    def delete_file(self, repository_path: str, file_path: str) -> None:
        client = self._get_client()
        client.delete(
            collection_name=self._collection,
            points_selector=self._filter(repository_path, file_path),
            wait=True,
        )

    def delete_repository(self, repository_path: str) -> None:
        client = self._get_client()
        client.delete(
            collection_name=self._collection,
            points_selector=self._filter(repository_path),
            wait=True,
        )

    # -- reads ------------------------------------------------------------ #

    def search(
        self,
        vector: Sequence[float],
        top_k: int,
        repository_path: str | None = None,
    ) -> list[VectorHit]:
        client = self._get_client()
        query_filter = (
            self._filter(repository_path) if repository_path is not None else None
        )
        points = client.query_points(
            collection_name=self._collection,
            query=list(vector),
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        ).points
        return [
            VectorHit(
                chunk_id=str(point.id),
                score=float(point.score),
                payload=dict(point.payload or {}),
            )
            for point in points
        ]

    def count(self, repository_path: str | None = None) -> int:
        client = self._get_client()
        result = client.count(
            collection_name=self._collection,
            count_filter=self._filter(repository_path) if repository_path else None,
            exact=True,
        )
        return int(result.count)

    def health_check(self) -> bool:
        try:
            self._get_client().get_collections()
            return True
        except Exception:  # noqa: BLE001 - probe must never raise
            logger.debug("qdrant health check failed", exc_info=True)
            return False

    # -- helpers ---------------------------------------------------------- #

    @staticmethod
    def _filter(repository_path: str, file_path: str | None = None) -> Any:
        from qdrant_client import models as qmodels

        conditions = [
            qmodels.FieldCondition(
                key="repository_path",
                match=qmodels.MatchValue(value=repository_path),
            )
        ]
        if file_path is not None:
            conditions.append(
                qmodels.FieldCondition(
                    key="file_path", match=qmodels.MatchValue(value=file_path)
                )
            )
        return qmodels.Filter(must=conditions)


def _existing_dimension(info: Any) -> int | None:
    """Read the vector size out of a ``CollectionInfo`` defensively."""
    try:
        params = info.config.params.vectors
    except AttributeError:  # pragma: no cover - client version drift
        return None
    size = getattr(params, "size", None)
    return int(size) if size is not None else None
