import pytest

from repomind.qdrant_store import QdrantVectorStore


@pytest.fixture
def qdrant_store():
    store = QdrantVectorStore(
        collection_name="repomind_test",
    )

    store.create_collection(
        vector_size=3,
    )

    yield store

    store.client.delete_collection(
        collection_name="repomind_test",
    )


def test_add_and_search(qdrant_store):
    qdrant_store.add(
        point_id=1,
        vector=[1.0, 0.0, 0.0],
        payload={
            "repository_path": "repo-a",
            "name": "authenticate",
        },
    )

    results = qdrant_store.search(
        query_vector=[1.0, 0.0, 0.0],
        top_k=1,
    )

    assert len(results) == 1
    assert results[0].payload["name"] == "authenticate"


def test_delete_repository(qdrant_store):
    qdrant_store.add(
        point_id=1,
        vector=[1.0, 0.0, 0.0],
        payload={
            "repository_path": "repo-a",
            "name": "authenticate",
        },
    )

    qdrant_store.add(
        point_id=2,
        vector=[0.0, 1.0, 0.0],
        payload={
            "repository_path": "repo-b",
            "name": "calculate_total",
        },
    )

    qdrant_store.delete_repository("repo-a")

    results = qdrant_store.search(
        query_vector=[1.0, 0.0, 0.0],
        top_k=10,
    )

    names = [
        result.payload["name"]
        for result in results
    ]

    assert "authenticate" not in names
    assert "calculate_total" in names