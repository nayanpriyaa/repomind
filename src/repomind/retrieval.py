"""Retrieval: semantic, keyword and hybrid.

Hybrid uses Reciprocal Rank Fusion rather than a weighted sum of raw scores.
Cosine similarity (roughly 0..1) and BM25 (unbounded, corpus-dependent) are not
comparable, and normalising them per query is unstable when one list is short.
RRF only consumes ranks:

    score(d) = sum over lists of 1 / (k + rank(d))

with ``k = 60``, the value from the original Cormack et al. TREC work. Large ``k``
flattens the contribution of top ranks; small ``k`` lets a single list dominate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

from .embeddings import Embedder
from .keyword_search import KeywordHit, KeywordIndex
from .models import ChunkType, Language, RetrievedChunk, SearchMode
from .vector_store import VectorHit, VectorStore

logger = logging.getLogger(__name__)

DEFAULT_RRF_K = 60
_CANDIDATE_MULTIPLIER = 3
_MIN_CANDIDATES = 20


@dataclass(frozen=True, slots=True)
class RetrievalRequest:
    """One retrieval call."""

    query: str
    mode: SearchMode = SearchMode.HYBRID
    top_k: int = 5
    repository_path: str | None = None


class RetrievalService:
    """Executes retrieval strategies and returns normalised domain results."""

    def __init__(
        self,
        vector_store: VectorStore,
        keyword_index: KeywordIndex,
        embedder: Embedder,
        rrf_k: int = DEFAULT_RRF_K,
    ) -> None:
        self._vectors = vector_store
        self._keywords = keyword_index
        self._embedder = embedder
        self._rrf_k = rrf_k

    def search(self, request: RetrievalRequest) -> list[RetrievedChunk]:
        """Dispatch to the requested strategy."""
        if not request.query.strip():
            return []
        if request.mode is SearchMode.SEMANTIC:
            return self.semantic_search(
                request.query, request.top_k, request.repository_path
            )
        if request.mode is SearchMode.KEYWORD:
            return self.keyword_search(
                request.query, request.top_k, request.repository_path
            )
        return self.hybrid_search(
            request.query, request.top_k, request.repository_path
        )

    def semantic_search(
        self, query: str, top_k: int = 5, repository_path: str | None = None
    ) -> list[RetrievedChunk]:
        """Dense vector search over Qdrant."""
        vector = self._embedder.embed_query(query)
        hits = self._vectors.search(vector, top_k, repository_path)
        return [
            _from_vector_hit(hit, rank, "semantic")
            for rank, hit in enumerate(hits, start=1)
        ]

    def keyword_search(
        self, query: str, top_k: int = 5, repository_path: str | None = None
    ) -> list[RetrievedChunk]:
        """Lexical BM25 search over SQLite FTS5."""
        hits = self._keywords.search(query, top_k, repository_path)
        return [
            _from_keyword_hit(hit, rank, "keyword")
            for rank, hit in enumerate(hits, start=1)
        ]

    def hybrid_search(
        self, query: str, top_k: int = 5, repository_path: str | None = None
    ) -> list[RetrievedChunk]:
        """Fuse dense and lexical rankings with Reciprocal Rank Fusion.

        Each backend is asked for more candidates than ``top_k`` so that fusion
        has room to promote a document that ranks moderately well in both lists
        over one that ranks first in only one.
        """
        candidates = max(top_k * _CANDIDATE_MULTIPLIER, _MIN_CANDIDATES)
        semantic = self.semantic_search(query, candidates, repository_path)
        keyword = self.keyword_search(query, candidates, repository_path)
        return reciprocal_rank_fusion(
            semantic, keyword, top_k=top_k, k=self._rrf_k
        )


def reciprocal_rank_fusion(
    semantic: Sequence[RetrievedChunk],
    keyword: Sequence[RetrievedChunk],
    top_k: int = 5,
    k: int = DEFAULT_RRF_K,
) -> list[RetrievedChunk]:
    """Fuse two ranked lists into one, keeping per-backend rank provenance."""
    scores: dict[str, float] = {}
    semantic_ranks: dict[str, int] = {}
    keyword_ranks: dict[str, int] = {}
    by_id: dict[str, RetrievedChunk] = {}

    for rank, chunk in enumerate(semantic, start=1):
        scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
        semantic_ranks[chunk.chunk_id] = rank
        by_id.setdefault(chunk.chunk_id, chunk)

    for rank, chunk in enumerate(keyword, start=1):
        scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
        keyword_ranks[chunk.chunk_id] = rank
        by_id.setdefault(chunk.chunk_id, chunk)

    ordered = sorted(
        by_id.values(),
        key=lambda chunk: (
            -scores[chunk.chunk_id],
            semantic_ranks.get(chunk.chunk_id, 10**6),
            chunk.chunk_id,
        ),
    )

    fused: list[RetrievedChunk] = []
    for chunk in ordered[:top_k]:
        semantic_rank = semantic_ranks.get(chunk.chunk_id)
        keyword_rank = keyword_ranks.get(chunk.chunk_id)
        if semantic_rank is not None and keyword_rank is not None:
            match_type = "hybrid"
        elif semantic_rank is not None:
            match_type = "semantic"
        else:
            match_type = "keyword"
        fused.append(
            RetrievedChunk(
                chunk_id=chunk.chunk_id,
                score=scores[chunk.chunk_id],
                repository_path=chunk.repository_path,
                file_path=chunk.file_path,
                language=chunk.language,
                chunk_type=chunk.chunk_type,
                symbol=chunk.symbol,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                content=chunk.content,
                match_type=match_type,
                semantic_rank=semantic_rank,
                keyword_rank=keyword_rank,
            )
        )
    return fused


def _from_vector_hit(hit: VectorHit, rank: int, match_type: str) -> RetrievedChunk:
    payload = hit.payload
    return RetrievedChunk(
        chunk_id=hit.chunk_id,
        score=hit.score,
        repository_path=str(payload.get("repository_path", "")),
        file_path=str(payload.get("file_path", "")),
        language=_language(payload.get("language")),
        chunk_type=_chunk_type(payload.get("chunk_type")),
        symbol=str(payload.get("symbol", "")),
        start_line=int(payload.get("start_line", 0) or 0),
        end_line=int(payload.get("end_line", 0) or 0),
        content=str(payload.get("content", "")),
        match_type=match_type,
        semantic_rank=rank,
    )


def _from_keyword_hit(hit: KeywordHit, rank: int, match_type: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=hit.chunk_id,
        score=hit.score,
        repository_path=hit.repository_path,
        file_path=hit.file_path,
        language=_language(hit.language),
        chunk_type=_chunk_type(hit.chunk_type),
        symbol=hit.symbol,
        start_line=hit.start_line,
        end_line=hit.end_line,
        content=hit.content,
        match_type=match_type,
        keyword_rank=rank,
    )


def _language(value: object) -> Language:
    try:
        return Language(str(value))
    except ValueError:
        return Language.UNKNOWN


def _chunk_type(value: object) -> ChunkType:
    try:
        return ChunkType(str(value))
    except ValueError:
        return ChunkType.MODULE
