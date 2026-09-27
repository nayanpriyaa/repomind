"""Integration tests against a real Qdrant server.

Run with:  QDRANT_HOST=localhost pytest -m integration
Skipped unless ``qdrant-client`` is installed and the server answers.
"""

from __future__ import annotations

import os
import uuid

import pytest

from conftest import make_chunk
from repomind.vector_store import VectorRecord

pytestmark = pytest.mark.integration

qdrant_client = pytest.importorskip("qdrant_client")

from repomind.qdrant_store import QdrantVectorStore  # noqa: E402

HOST = os.environ.get("QDRANT_HOST", "localhost")
PORT = int(os.environ.get("QDRANT_PORT", "6333"))


@pytest.fixture()
def store():
    collection = f"repomind_test_{uuid.uuid4().hex[:8]}"
    built = QdrantVectorStore(host=HOST, port=PORT, collection=collection, timeout=5.0)
    if not built.health_check():
        pytest.skip(f"no qdrant server at {HOST}:{PORT}")
    built.ensure_collection(4)
    yield built
    built._get_client().delete_collection(collection)


def record(chunk_id_seed: str, vector: list[float], file_path: str = "a.py", repository_path: str = "/repositories/sample") -> VectorRecord:
    from repomind.ids import chunk_id

    identifier = chunk_id(repository_path, file_path, "function", chunk_id_seed, 1, 5)
    chunk = make_chunk(identifier, symbol=chunk_id_seed, file_path=file_path, repository_path=repository_path)
    return VectorRecord.from_chunk(chunk, vector)


def test_ensure_collection_is_idempotent(store) -> None:
    store.ensure_collection(4)
    assert store.health_check() is True


def test_dimension_mismatch_is_rejected(store) -> None:
    with pytest.raises(ValueError):
        store.ensure_collection(8)


def test_upsert_and_search_round_trip(store) -> None:
    store.upsert([record("near", [1.0, 0.0, 0.0, 0.0]), record("far", [0.0, 1.0, 0.0, 0.0], file_path="b.py")])
    hits = store.search([1.0, 0.0, 0.0, 0.0], top_k=2)
    assert hits[0].payload["symbol"] == "near"
    assert hits[0].score >= hits[1].score


def test_payload_survives_the_round_trip(store) -> None:
    store.upsert([record("one", [1.0, 0.0, 0.0, 0.0])])
    payload = store.search([1.0, 0.0, 0.0, 0.0], top_k=1)[0].payload
    assert payload["file_path"] == "a.py"
    assert payload["start_line"] == 1 and payload["end_line"] == 2
    assert payload["language"] == "python"


def test_upsert_is_idempotent_for_stable_ids(store) -> None:
    store.upsert([record("one", [1.0, 0.0, 0.0, 0.0])])
    store.upsert([record("one", [1.0, 0.0, 0.0, 0.0])])
    assert store.count() == 1


def test_repository_filter(store) -> None:
    store.upsert([record("one", [1.0, 0.0, 0.0, 0.0], repository_path="/repositories/one")])
    store.upsert([record("two", [1.0, 0.0, 0.0, 0.0], repository_path="/repositories/two")])
    hits = store.search([1.0, 0.0, 0.0, 0.0], top_k=5, repository_path="/repositories/one")
    assert {hit.payload["repository_path"] for hit in hits} == {"/repositories/one"}


def test_delete_file_and_repository(store) -> None:
    store.upsert([record("a", [1.0, 0.0, 0.0, 0.0], file_path="a.py"), record("b", [0.0, 1.0, 0.0, 0.0], file_path="b.py")])
    store.delete_file("/repositories/sample", "a.py")
    assert store.count("/repositories/sample") == 1
    store.delete_repository("/repositories/sample")
    assert store.count("/repositories/sample") == 0
