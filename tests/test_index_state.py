"""SQLite index state: the new/modified/unchanged/deleted partition."""

from __future__ import annotations

from conftest import make_chunk, make_source

from repomind.index_state import IndexState
from repomind.models import RepositoryStatus

REPO = "/repositories/sample"


def test_diff_reports_every_file_as_new_on_a_cold_index(index_state: IndexState) -> None:
    diff = index_state.diff(REPO, [make_source("a = 1", "a.py"), make_source("b = 2", "b.py")])
    assert sorted(diff.new) == ["a.py", "b.py"]
    assert diff.modified == [] and diff.unchanged == [] and diff.deleted == []


def test_unchanged_files_are_detected_by_digest(index_state: IndexState) -> None:
    source = make_source("a = 1", "a.py")
    index_state.record_file(source, [make_chunk("id-1", file_path="a.py")])
    diff = index_state.diff(REPO, [source])
    assert diff.unchanged == ["a.py"]
    assert diff.requires_work is False


def test_modified_files_are_detected_by_digest(index_state: IndexState) -> None:
    index_state.record_file(make_source("a = 1", "a.py"), [make_chunk("id-1", file_path="a.py")])
    diff = index_state.diff(REPO, [make_source("a = 2", "a.py")])
    assert diff.modified == ["a.py"]
    assert diff.requires_work is True


def test_deleted_files_are_detected_by_absence(index_state: IndexState) -> None:
    index_state.record_file(make_source("a = 1", "a.py"), [make_chunk("id-1", file_path="a.py")])
    diff = index_state.diff(REPO, [])
    assert diff.deleted == ["a.py"]


def test_reverting_a_file_makes_it_unchanged_again(index_state: IndexState) -> None:
    original = make_source("a = 1", "a.py")
    index_state.record_file(original, [make_chunk("id-1", file_path="a.py")])
    index_state.record_file(make_source("a = 2", "a.py"), [make_chunk("id-2", file_path="a.py")])
    assert index_state.diff(REPO, [original]).modified == ["a.py"]
    index_state.record_file(original, [make_chunk("id-1", file_path="a.py")])
    assert index_state.diff(REPO, [original]).unchanged == ["a.py"]


def test_recording_a_file_replaces_its_previous_chunks(index_state: IndexState) -> None:
    source = make_source("a = 1", "a.py")
    index_state.record_file(source, [make_chunk("old-1", file_path="a.py"), make_chunk("old-2", file_path="a.py")])
    index_state.record_file(source, [make_chunk("new-1", file_path="a.py")])
    assert index_state.chunk_ids_for_file(REPO, "a.py") == ["new-1"]


def test_delete_file_removes_state_and_chunks(index_state: IndexState) -> None:
    index_state.record_file(make_source("a = 1", "a.py"), [make_chunk("id-1", file_path="a.py")])
    assert index_state.delete_file(REPO, "a.py") == 1
    assert index_state.known_hashes(REPO) == {}
    assert index_state.chunk_ids_for_file(REPO, "a.py") == []


def test_delete_repository_removes_everything(index_state: IndexState) -> None:
    index_state.record_file(make_source("a = 1", "a.py"), [make_chunk("id-1", file_path="a.py")])
    index_state.record_file(make_source("b = 2", "b.py"), [make_chunk("id-2", file_path="b.py")])
    index_state.touch_repository(REPO)
    assert index_state.delete_repository(REPO) == 2
    assert index_state.status(REPO).indexed is False


def test_status_aggregates_counts_and_languages(index_state: IndexState) -> None:
    index_state.record_file(make_source("a = 1", "a.py"), [make_chunk("id-1", file_path="a.py")])
    index_state.record_file(make_source("b = 2", "b.py"), [make_chunk("id-2", file_path="b.py"), make_chunk("id-3", file_path="b.py")])
    index_state.touch_repository(REPO)
    status = index_state.status(REPO)
    assert isinstance(status, RepositoryStatus)
    assert status.indexed is True
    assert status.file_count == 2
    assert status.chunk_count == 3
    assert status.languages == {"python": 2}
    assert status.last_indexed_at is not None


def test_status_of_an_unknown_repository_is_empty(index_state: IndexState) -> None:
    status = index_state.status("/repositories/never-seen")
    assert status.indexed is False and status.file_count == 0


def test_repositories_are_isolated_from_each_other(index_state: IndexState) -> None:
    index_state.record_file(make_source("a = 1", "a.py", repository_path="/repositories/one"), [make_chunk("id-1", repository_path="/repositories/one")])
    index_state.record_file(make_source("a = 1", "a.py", repository_path="/repositories/two"), [make_chunk("id-2", repository_path="/repositories/two")])
    index_state.delete_repository("/repositories/one")
    assert index_state.known_hashes("/repositories/two") != {}


def test_initialize_is_idempotent(index_state: IndexState) -> None:
    index_state.initialize()
    index_state.initialize()
    assert index_state.health_check() is True


def test_list_repositories_returns_touched_repositories(index_state: IndexState) -> None:
    index_state.record_file(make_source("a = 1", "a.py"), [make_chunk("id-1")])
    index_state.touch_repository(REPO)
    assert [item.repository_path for item in index_state.list_repositories()] == [REPO]
