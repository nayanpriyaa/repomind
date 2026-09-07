from pathlib import Path

from repomind.models import CodeChunk
from repomind.vector_store import VectorStore


def create_chunk(name: str) -> CodeChunk:
    return CodeChunk(
        file_path=Path("service.py"),
        chunk_type="FUNCTION",
        name=name,
        start_line=1,
        end_line=5,
        content=f"def {name}():",
    )


def test_add_chunk():
    store = VectorStore()

    chunk = create_chunk("authenticate")

    store.add(
        chunk,
        [1.0, 0.0, 0.0],
    )

    assert len(store.items) == 1
    assert store.items[0].chunk.name == "authenticate"


def test_search_returns_most_similar_chunk():
    store = VectorStore()

    authenticate = create_chunk("authenticate")
    calculate_total = create_chunk("calculate_total")

    store.add(
        authenticate,
        [1.0, 0.0, 0.0],
    )

    store.add(
        calculate_total,
        [0.0, 1.0, 0.0],
    )

    results = store.search(
        [0.9, 0.1, 0.0],
        top_k=1,
    )

    assert len(results) == 1

    chunk, similarity = results[0]

    assert chunk.name == "authenticate"
    assert similarity > 0.9


def test_search_respects_top_k():
    store = VectorStore()

    store.add(
        create_chunk("authenticate"),
        [1.0, 0.0, 0.0],
    )

    store.add(
        create_chunk("calculate_total"),
        [0.0, 1.0, 0.0],
    )

    store.add(
        create_chunk("health_check"),
        [0.0, 0.0, 1.0],
    )

    results = store.search(
        [1.0, 0.0, 0.0],
        top_k=2,
    )

    assert len(results) == 2
    assert results[0][0].name == "authenticate"

def test_delete_repository():
  store = VectorStore()