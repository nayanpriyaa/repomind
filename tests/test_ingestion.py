"""Ingestion pipeline: incremental behaviour and cross-store consistency."""

from __future__ import annotations

from pathlib import Path

from repomind.container import ServiceContainer


def index(container: ServiceContainer, repository: Path, force: bool = False):
    return container.ingestion.index_repository(str(repository.resolve()), force=force)


def test_first_index_stores_files_and_chunks(container, sample_repository: Path) -> None:
    report = index(container, sample_repository)
    assert report.files_indexed > 0
    assert report.chunks_indexed > 0
    assert report.files_unchanged == 0


def test_second_index_skips_everything(container, sample_repository: Path) -> None:
    first = index(container, sample_repository)
    second = index(container, sample_repository)
    assert second.files_indexed == 0
    assert second.chunks_indexed == 0
    assert second.files_unchanged == first.files_indexed


def test_modified_file_is_reindexed(container, sample_repository: Path) -> None:
    index(container, sample_repository)
    target = sample_repository / "app" / "auth.py"
    target.write_text(target.read_text() + "\n\ndef logout(session):\n    return None\n", encoding="utf-8")
    report = index(container, sample_repository)
    assert report.files_indexed == 1
    assert report.chunks_indexed > 0


def test_modified_file_does_not_leave_orphan_chunks(container, sample_repository: Path) -> None:
    index(container, sample_repository)
    repository = str(sample_repository.resolve())
    target = sample_repository / "app" / "auth.py"
    target.write_text("def only_one():\n    return 1\n", encoding="utf-8")
    index(container, sample_repository)
    remaining = container.index_state.chunk_ids_for_file(repository, "app/auth.py")
    assert len(remaining) == 1


def test_deleted_file_is_removed_from_every_store(container, sample_repository: Path) -> None:
    index(container, sample_repository)
    repository = str(sample_repository.resolve())
    (sample_repository / "app" / "auth.py").unlink()
    report = index(container, sample_repository)
    assert report.files_deleted == 1
    assert container.index_state.chunk_ids_for_file(repository, "app/auth.py") == []
    hits = container.keyword_index.search("authenticate", top_k=20, repository_path=repository)
    assert all(hit.file_path != "app/auth.py" for hit in hits)


def test_stores_stay_in_agreement(container, sample_repository: Path) -> None:
    index(container, sample_repository)
    repository = str(sample_repository.resolve())
    status = container.index_state.status(repository)
    assert status.chunk_count == container.keyword_index.count(repository)
    assert status.chunk_count == container.vector_store.count(repository)


def test_force_rebuilds_from_scratch(container, sample_repository: Path) -> None:
    index(container, sample_repository)
    report = index(container, sample_repository, force=True)
    assert report.files_unchanged == 0
    assert report.files_indexed > 0


def test_unreadable_file_does_not_abort_the_run(container, sample_repository: Path) -> None:
    report = index(container, sample_repository)
    assert report.files_skipped > 0
    assert report.files_indexed > 0


def test_skipped_files_are_reported_with_reasons(container, sample_repository: Path) -> None:
    report = index(container, sample_repository)
    reasons = {item.file_path: item.reason for item in report.skipped}
    assert reasons[".env"] == "secret file excluded"


def test_delete_repository_clears_all_state(container, sample_repository: Path) -> None:
    index(container, sample_repository)
    repository = str(sample_repository.resolve())
    container.ingestion.delete_repository(repository)
    assert container.index_state.status(repository).indexed is False
    assert container.keyword_index.count(repository) == 0
    assert container.vector_store.count(repository) == 0


def test_two_repositories_do_not_interfere(container, tmp_path: Path) -> None:
    from conftest import write_sample_repository

    first = write_sample_repository(tmp_path / "a")
    second = write_sample_repository(tmp_path / "b")
    index(container, first)
    index(container, second)
    container.ingestion.delete_repository(str(first.resolve()))
    assert container.index_state.status(str(second.resolve())).indexed is True
