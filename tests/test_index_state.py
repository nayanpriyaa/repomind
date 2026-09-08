from pathlib import Path

from repomind.index_state import IndexState


def test_file_hash_is_saved_and_retrieved(tmp_path: Path):
    database_path = tmp_path / "index.db"

    state = IndexState(
        database_path=str(database_path)
    )

    state.save_file_hash(
        repository_path="repo-a",
        file_path="src/main.py",
        file_hash="abc123",
    )

    result = state.get_file_hash(
        repository_path="repo-a",
        file_path="src/main.py",
    )

    assert result == "abc123"

    state.close()


def test_missing_file_returns_none(tmp_path: Path):
    database_path = tmp_path / "index.db"

    state = IndexState(
        database_path=str(database_path)
    )

    result = state.get_file_hash(
        repository_path="repo-a",
        file_path="src/missing.py",
    )

    assert result is None

    state.close()

def test_get_indexed_files(tmp_path: Path):
    database_path = tmp_path / "index.db"

    state = IndexState(
        database_path=str(database_path)
    )

    state.save_file_hash(
        repository_path="repo-a",
        file_path="src/main.py",
        file_hash="hash-1",
    )

    state.save_file_hash(
        repository_path="repo-a",
        file_path="src/auth.py",
        file_hash="hash-2",
    )

    state.save_file_hash(
        repository_path="repo-b",
        file_path="src/user.py",
        file_hash="hash-3",
    )

    files = state.get_indexed_files(
        repository_path="repo-a"
    )

    assert set(files) == {
        "src/main.py",
        "src/auth.py",
    }

    state.close()


def test_delete_file_record(tmp_path: Path):
    database_path = tmp_path / "index.db"

    state = IndexState(
        database_path=str(database_path)
    )

    state.save_file_hash(
        repository_path="repo-a",
        file_path="src/main.py",
        file_hash="hash-1",
    )

    state.delete_file_record(
        repository_path="repo-a",
        file_path="src/main.py",
    )

    result = state.get_file_hash(
        repository_path="repo-a",
        file_path="src/main.py",
    )

    assert result is None

    state.close()

def test_deleted_file_is_removed_from_state(tmp_path: Path):
    database_path = tmp_path / "index.db"

    state = IndexState(
        database_path=str(database_path)
    )

    state.save_file_hash(
        repository_path="repo-a",
        file_path="src/auth.py",
        file_hash="abc123",
    )

    state.save_file_hash(
        repository_path="repo-a",
        file_path="src/user.py",
        file_hash="def456",
    )

    current_files = {
        "src/user.py",
    }

    indexed_files = state.get_indexed_files(
        repository_path="repo-a"
    )

    for indexed_file in indexed_files:
        if indexed_file not in current_files:
            state.delete_file_record(
                repository_path="repo-a",
                file_path=indexed_file,
            )

    remaining_files = state.get_indexed_files(
        repository_path="repo-a"
    )

    assert remaining_files == ["src/user.py"]

    state.close()


def test_existing_file_hash_is_updated(tmp_path: Path):
    database_path = tmp_path / "index.db"

    state = IndexState(
        database_path=str(database_path)
    )

    state.save_file_hash(
        repository_path="repo-a",
        file_path="src/main.py",
        file_hash="old-hash",
    )

    state.save_file_hash(
        repository_path="repo-a",
        file_path="src/main.py",
        file_hash="new-hash",
    )

    result = state.get_file_hash(
        repository_path="repo-a",
        file_path="src/main.py",
    )

    assert result == "new-hash"

    state.close()