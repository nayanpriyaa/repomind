"""Incremental indexing pipeline.

Orchestrates scan -> diff -> parse -> embed -> store and owns the consistency
rules between the three stores (SQLite state, FTS5 index, Qdrant collection).

Consistency strategy: there is no distributed transaction across SQLite and
Qdrant, so the pipeline is made *idempotent* instead. Deletes always run before
writes, chunk IDs are deterministic, and a re-run of a partially failed index
converges to the correct state because unchanged files are skipped by digest and
changed files are fully rewritten.
"""

from __future__ import annotations

import logging
import time
from typing import Sequence

from .embeddings import Embedder, iter_batches
from .index_state import IndexState
from .keyword_search import KeywordIndex
from .models import CodeChunk, IndexReport, SkippedFile, SourceFile
from .parser import parse_file
from .scanner import RepositoryScanner
from .vector_store import VectorRecord, VectorStore

logger = logging.getLogger(__name__)


class IngestionService:
    """Indexes repositories and keeps every store in agreement."""

    def __init__(
        self,
        scanner: RepositoryScanner,
        index_state: IndexState,
        keyword_index: KeywordIndex,
        vector_store: VectorStore,
        embedder: Embedder,
        max_chunk_characters: int = 6_000,
        embedding_batch_size: int = 32,
    ) -> None:
        self._scanner = scanner
        self._state = index_state
        self._keywords = keyword_index
        self._vectors = vector_store
        self._embedder = embedder
        self._max_chunk_characters = max_chunk_characters
        self._embedding_batch_size = max(1, embedding_batch_size)

    def initialize(self) -> None:
        """Create every persistent structure the pipeline writes to."""
        self._state.initialize()
        self._keywords.initialize()
        self._vectors.ensure_collection(self._embedder.dimension)

    def index_repository(
        self, repository_path: str, force: bool = False
    ) -> IndexReport:
        """Index or re-index ``repository_path``.

        With ``force=True`` all prior state for the repository is dropped first,
        which turns the run into a full rebuild.
        """
        started = time.perf_counter()
        repository_path = str(repository_path)
        self.initialize()

        if force:
            logger.info("force re-index requested for %s", repository_path)
            self._purge_repository(repository_path)

        scan = self._scanner.scan(repository_path)
        by_path = {source.file_path: source for source in scan.files}
        diff = self._state.diff(repository_path, scan.files)

        chunks_deleted = 0
        for file_path in diff.deleted:
            chunks_deleted += self._forget_file(repository_path, file_path)

        targets = [by_path[path] for path in (*diff.new, *diff.modified)]
        failures: list[SkippedFile] = []
        chunks_indexed = 0
        files_indexed = 0

        for source in targets:
            try:
                chunks_indexed += self._index_file(source)
                files_indexed += 1
            except Exception as exc:  # noqa: BLE001 - never abort the whole run
                logger.exception("failed to index %s", source.file_path)
                failures.append(
                    SkippedFile(
                        file_path=source.file_path,
                        reason=f"indexing error: {exc.__class__.__name__}",
                    )
                )

        self._state.touch_repository(repository_path)
        duration = time.perf_counter() - started
        logger.info(
            "indexed %s: %d files, %d chunks in %.2fs",
            repository_path,
            files_indexed,
            chunks_indexed,
            duration,
        )
        return IndexReport(
            repository_path=repository_path,
            files_scanned=len(scan.files),
            files_indexed=files_indexed,
            files_skipped=len(scan.skipped) + len(failures),
            files_unchanged=len(diff.unchanged),
            files_deleted=len(diff.deleted),
            chunks_indexed=chunks_indexed,
            chunks_deleted=chunks_deleted,
            duration_seconds=duration,
            skipped=[*scan.skipped, *failures],
        )

    def delete_repository(self, repository_path: str) -> int:
        """Remove a repository from every store. Returns chunks removed."""
        return self._purge_repository(repository_path)

    # -- internals -------------------------------------------------------- #

    def _index_file(self, source: SourceFile) -> int:
        """Re-chunk, re-embed and re-store one file. Returns chunks written."""
        chunks = parse_file(source, self._max_chunk_characters)

        # Delete first so a file that now produces zero chunks still loses its
        # stale rows, and so modified files never accumulate orphans.
        self._vectors.delete_file(source.repository_path, source.file_path)
        self._keywords.delete_file(source.repository_path, source.file_path)

        if chunks:
            self._vectors.upsert(self._embed_chunks(chunks))
            self._keywords.index_chunks(chunks)
        self._state.record_file(source, chunks)
        return len(chunks)

    def _embed_chunks(self, chunks: Sequence[CodeChunk]) -> list[VectorRecord]:
        """Embed chunks in batches and pair each vector with its payload."""
        records: list[VectorRecord] = []
        texts = [_embedding_text(chunk) for chunk in chunks]
        position = 0
        for batch in iter_batches(texts, self._embedding_batch_size):
            for offset, vector in enumerate(self._embedder.embed_documents(batch)):
                records.append(VectorRecord.from_chunk(chunks[position + offset], vector))
            position += len(batch)
        return records

    def _forget_file(self, repository_path: str, file_path: str) -> int:
        removed = self._state.delete_file(repository_path, file_path)
        self._keywords.delete_file(repository_path, file_path)
        self._vectors.delete_file(repository_path, file_path)
        return removed

    def _purge_repository(self, repository_path: str) -> int:
        removed = self._state.delete_repository(repository_path)
        self._keywords.delete_repository(repository_path)
        self._vectors.delete_repository(repository_path)
        return removed


def _embedding_text(chunk: CodeChunk) -> str:
    """Prefix the embedded text with structural metadata.

    The file path, symbol and chunk kind carry real signal for questions such as
    "where is authentication implemented", so they are embedded alongside the
    body rather than being left as payload-only metadata.
    """
    header = f"{chunk.file_path} | {chunk.chunk_type.value} {chunk.symbol}"
    return f"{header}\n{chunk.content}"
