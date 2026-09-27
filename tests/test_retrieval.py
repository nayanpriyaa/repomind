"""Retrieval strategies and Reciprocal Rank Fusion."""

from __future__ import annotations

from repomind.embeddings import HashingEmbedder
from repomind.keyword_search import KeywordIndex
from repomind.models import ChunkType, Language, RetrievedChunk, SearchMode
from repomind.retrieval import (
    DEFAULT_RRF_K,
    RetrievalRequest,
    RetrievalService,
    reciprocal_rank_fusion,
)
from repomind.vector_store import InMemoryVectorStore, VectorRecord

from conftest import make_chunk


def retrieved(chunk_id: str, score: float = 1.0) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        score=score,
        repository_path="/repositories/sample",
        file_path=f"{chunk_id}.py",
        language=Language.PYTHON,
        chunk_type=ChunkType.FUNCTION,
        symbol=chunk_id,
        start_line=1,
        end_line=5,
        content=f"def {chunk_id}(): ...",
    )


def test_rrf_promotes_documents_present_in_both_lists() -> None:
    semantic = [retrieved("a"), retrieved("shared"), retrieved("b")]
    keyword = [retrieved("c"), retrieved("shared"), retrieved("d")]
    fused = reciprocal_rank_fusion(semantic, keyword, top_k=3)
    assert fused[0].chunk_id == "shared"


def test_rrf_score_matches_the_formula() -> None:
    fused = reciprocal_rank_fusion([retrieved("x")], [retrieved("x")], top_k=1)
    expected = 2 * (1.0 / (DEFAULT_RRF_K + 1))
    assert abs(fused[0].score - expected) < 1e-12


def test_rrf_records_per_backend_ranks_and_match_type() -> None:
    fused = reciprocal_rank_fusion([retrieved("a"), retrieved("b")], [retrieved("b")], top_k=2)
    by_id = {chunk.chunk_id: chunk for chunk in fused}
    assert by_id["b"].match_type == "hybrid"
    assert by_id["b"].semantic_rank == 2 and by_id["b"].keyword_rank == 1
    assert by_id["a"].match_type == "semantic" and by_id["a"].keyword_rank is None


def test_rrf_deduplicates_by_chunk_id() -> None:
    fused = reciprocal_rank_fusion([retrieved("a")], [retrieved("a")], top_k=10)
    assert len(fused) == 1


def test_rrf_handles_one_empty_list() -> None:
    fused = reciprocal_rank_fusion([retrieved("a")], [], top_k=5)
    assert [chunk.chunk_id for chunk in fused] == ["a"]
    assert fused[0].match_type == "semantic"


def test_rrf_is_deterministic_for_tied_scores() -> None:
    semantic = [retrieved("b"), retrieved("a")]
    first = reciprocal_rank_fusion(semantic, [], top_k=2)
    second = reciprocal_rank_fusion(semantic, [], top_k=2)
    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]


def test_rrf_respects_top_k() -> None:
    lists = [retrieved(name) for name in "abcdefgh"]
    assert len(reciprocal_rank_fusion(lists, [], top_k=3)) == 3


def build_service(tmp_path) -> RetrievalService:
    embedder = HashingEmbedder()
    store = InMemoryVectorStore()
    store.ensure_collection(embedder.dimension)
    keywords = KeywordIndex(tmp_path / "state.db")
    keywords.initialize()

    chunks = [
        make_chunk("auth", symbol="authenticate", file_path="app/auth.py", content="def authenticate(user, password):\n    return verify_password(user, password)\n"),
        make_chunk("db", symbol="connect", file_path="app/database.py", content="def connect(dsn):\n    return engine.connect(dsn)\n"),
    ]
    keywords.index_chunks(chunks)
    store.upsert([VectorRecord.from_chunk(chunk, embedder.embed_query(chunk.content)) for chunk in chunks])
    return RetrievalService(store, keywords, embedder)


def test_semantic_search_returns_normalised_domain_objects(tmp_path) -> None:
    hits = build_service(tmp_path).semantic_search("verify a password", top_k=2)
    assert hits and isinstance(hits[0], RetrievedChunk)
    assert hits[0].language is Language.PYTHON
    assert hits[0].semantic_rank == 1 and hits[0].match_type == "semantic"


def test_keyword_search_returns_normalised_domain_objects(tmp_path) -> None:
    hits = build_service(tmp_path).keyword_search("authenticate", top_k=2)
    assert hits[0].file_path == "app/auth.py"
    assert hits[0].keyword_rank == 1 and hits[0].match_type == "keyword"


def test_search_dispatches_on_mode(tmp_path) -> None:
    service = build_service(tmp_path)
    for mode in SearchMode:
        hits = service.search(RetrievalRequest(query="authenticate", mode=mode, top_k=2))
        assert hits, f"{mode} returned nothing"


def test_blank_query_short_circuits(tmp_path) -> None:
    assert build_service(tmp_path).search(RetrievalRequest(query="   ")) == []


def test_repository_filter_excludes_other_repositories(tmp_path) -> None:
    service = build_service(tmp_path)
    assert service.search(RetrievalRequest(query="authenticate", repository_path="/repositories/other")) == []
