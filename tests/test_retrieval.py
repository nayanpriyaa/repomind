from pathlib import Path

from repomind.retrieval import RepositorySearcher


class FakeEmbeddingModel:

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * 384

        if "authenticate" in text:
            vector[0] = 1.0
        else:
            vector[1] = 1.0

        return vector


def create_test_searcher(
    tmp_path: Path,
    collection_name: str,
) -> RepositorySearcher:

    searcher = RepositorySearcher()

    searcher.vector_store = searcher.vector_store.__class__(
        collection_name=collection_name,
    )

    searcher.embedding_model = FakeEmbeddingModel()

    searcher.index_state.close()

    searcher.index_state = searcher.index_state.__class__(
        database_path=str(
            tmp_path / "index.db"
        )
    )

    return searcher


def test_index_repository(tmp_path: Path):
    repository = tmp_path / "repo"
    repository.mkdir()

    source_file = repository / "auth.py"

    source_file.write_text(
        """
def authenticate():
    return True
"""
    )

    searcher = create_test_searcher(
        tmp_path=tmp_path,
        collection_name=f"repomind_retrieval_test_{tmp_path.name}",
    )

    searcher.index_repository(
        str(repository)
    )

    results = searcher.search(
        query="authenticate",
        repository_path=str(repository),
    )

    assert len(results) == 1
    assert results[0].payload["name"] == "authenticate"

    searcher.index_state.close()


def test_incremental_indexing(tmp_path: Path):
    repository = tmp_path / "repo"
    repository.mkdir()

    source_file = repository / "auth.py"

    source_file.write_text(
        """
def authenticate():
    return True
"""
    )

    searcher = create_test_searcher(
        tmp_path=tmp_path,
        collection_name=f"repomind_incremental_test_{tmp_path.name}",
    )

    # First indexing.
    searcher.index_repository(
        str(repository)
    )

    results = searcher.search(
        query="authenticate",
        repository_path=str(repository),
    )

    assert len(results) == 1
    assert results[0].payload["name"] == "authenticate"

    # Second indexing:
    # The file has not changed, so it should be skipped.
    searcher.index_repository(
        str(repository)
    )

    results = searcher.search(
        query="authenticate",
        repository_path=str(repository),
    )

    assert len(results) == 1

    # Modify the file.
    source_file.write_text(
        """
def authenticate():
    return False
"""
    )

    searcher.index_repository(
        str(repository)
    )

    results = searcher.search(
        query="authenticate",
        repository_path=str(repository),
    )

    assert len(results) == 1
    assert "return False" in results[0].payload["content"]

    # Delete the file.
    source_file.unlink()

    searcher.index_repository(
        str(repository)
    )

    results = searcher.search(
        query="authenticate",
        repository_path=str(repository),
    )

    assert len(results) == 0

    searcher.index_state.close()