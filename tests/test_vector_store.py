"""Vector-store contract, verified against the in-memory implementation."""

from __future__ import annotations

import pytest

from conftest import make_chunk
from repomind.vector_store import InMemoryVectorStore, VectorRecord


def record(chunk_id: str, vector: list[float], repository_path: str = "/repositories/sample", file_path: str = "a.py") -> VectorRecord:
    return VectorRecord.from_chunk(make_chunk(chunk_id, file_path=file_path, repository_path=repository_path), vector)


def test_from_chunk_carries_the_citation_payload() -> None:
    built = record("a", [1.0, 0.0])
    assert built.payload["file_path"] == "a.py"
    assert built.payload["start_line"] == 1
    assert "content" in built.payload


def test_ensure_collection_rejects_a_dimension_change() -> None:
    store = InMemoryVectorStore()
    store.ensure_collection(384)
    store.ensure_collection(384)
    with pytest.raises(ValueError):
        store.ensure_collection(768)


def test_search_orders_by_similarity() -> None:
    store = InMemoryVectorStore()
    store.upsert([record("near", [1.0, 0.0]), record("far", [0.0, 1.0], file_path="b.py")])
    hits = store.search([1.0, 0.0], top_k=2)
    assert [hit.chunk_id for hit in hits] == ["near", "far"]
    assert hits[0].score > hits[1].score


def test_upsert_replaces_by_id() -> None:
    store = InMemoryVectorStore()
    store.upsert([record("same", [1.0, 0.0])])
    store.upsert([record("same", [0.0, 1.0])])
    assert store.count() == 1


def test_search_respects_top_k() -> None:
    store = InMemoryVectorStore()
    store.upsert([record(str(i), [1.0, float(i)], file_path=f"{i}.py") for i in range(10)])
    assert len(store.search([1.0, 0.0], top_k=3)) == 3


def test_search_filters_by_repository() -> None:
    store = InMemoryVectorStore()
    store.upsert([record("one", [1.0, 0.0], repository_path="/repositories/one")])
    store.upsert([record("two", [1.0, 0.0], repository_path="/repositories/two")])
    hits = store.search([1.0, 0.0], top_k=5, repository_path="/repositories/one")
    assert [hit.chunk_id for hit in hits] == ["one"]


def test_delete_file_is_scoped() -> None:
    store = InMemoryVectorStore()
    store.upsert([record("a", [1.0, 0.0], file_path="a.py"), record("b", [0.0, 1.0], file_path="b.py")])
    store.delete_file("/repositories/sample", "a.py")
    assert [hit.chunk_id for hit in store.search([1.0, 1.0], top_k=5)] == ["b"]


def test_delete_repository_is_scoped() -> None:
    store = InMemoryVectorStore()
    store.upsert([record("one", [1.0, 0.0], repository_path="/repositories/one")])
    store.upsert([record("two", [1.0, 0.0], repository_path="/repositories/two")])
    store.delete_repository("/repositories/one")
    assert store.count() == 1
    assert store.count("/repositories/two") == 1


def test_zero_vectors_do_not_divide_by_zero() -> None:
    store = InMemoryVectorStore()
    store.upsert([record("z", [0.0, 0.0])])
    assert store.search([0.0, 0.0], top_k=1)[0].score == 0.0


def test_health_check_is_always_true() -> None:
    assert InMemoryVectorStore().health_check() is True
