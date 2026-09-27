"""Digest and identifier determinism - the foundation of incremental indexing."""

from __future__ import annotations

from pathlib import Path

from repomind.file_hash import hash_bytes, hash_file, hash_text
from repomind.ids import chunk_id, repository_key


def test_hash_text_matches_hash_bytes() -> None:
    assert hash_text("hello") == hash_bytes(b"hello")


def test_hash_is_sensitive_to_single_character_changes() -> None:
    assert hash_text("value = 1") != hash_text("value = 2")


def test_hash_file_streams_the_same_digest(tmp_path: Path) -> None:
    target = tmp_path / "big.txt"
    payload = b"x" * 200_000
    target.write_bytes(payload)
    assert hash_file(target) == hash_bytes(payload)


def test_chunk_id_is_stable_for_identical_coordinates() -> None:
    first = chunk_id("/repo", "app/auth.py", "function", "login", 10, 20)
    second = chunk_id("/repo", "app/auth.py", "function", "login", 10, 20)
    assert first == second


def test_chunk_id_changes_with_any_coordinate() -> None:
    base = chunk_id("/repo", "app/auth.py", "function", "login", 10, 20)
    assert base != chunk_id("/other", "app/auth.py", "function", "login", 10, 20)
    assert base != chunk_id("/repo", "app/main.py", "function", "login", 10, 20)
    assert base != chunk_id("/repo", "app/auth.py", "method", "login", 10, 20)
    assert base != chunk_id("/repo", "app/auth.py", "function", "logout", 10, 20)
    assert base != chunk_id("/repo", "app/auth.py", "function", "login", 11, 20)
    assert base != chunk_id("/repo", "app/auth.py", "function", "login", 10, 21)


def test_chunk_id_is_uuid_shaped_for_qdrant() -> None:
    import uuid

    value = chunk_id("/repo", "a.py", "function", "f", 1, 2)
    assert uuid.UUID(value).version == 5


def test_chunk_id_separator_prevents_field_collisions() -> None:
    left = chunk_id("/repo", "a.py", "function", "ab", 1, 2)
    right = chunk_id("/repo", "a.py", "function", "a", 1, 2)
    assert left != right


def test_repository_key_normalises_trailing_slashes() -> None:
    assert repository_key("/repositories/demo/") == "/repositories/demo"
    assert repository_key("/") == "/"
