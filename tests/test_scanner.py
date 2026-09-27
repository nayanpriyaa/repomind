"""Scanner behaviour: what gets indexed, what gets refused, and why."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from repomind.models import Language
from repomind.scanner import (
    RepositoryScanner,
    ScannerConfig,
    classify,
    is_secret_file,
    looks_binary,
)


def reasons(result) -> dict[str, str]:
    return {item.file_path: item.reason for item in result.skipped}


def test_scan_accepts_supported_sources(sample_repository: Path) -> None:
    result = RepositoryScanner().scan(sample_repository)
    accepted = {source.file_path for source in result.files}
    assert "app/auth.py" in accepted
    assert "README.md" in accepted


def test_scan_prunes_ignored_directories(sample_repository: Path) -> None:
    result = RepositoryScanner().scan(sample_repository)
    accepted = {source.file_path for source in result.files}
    assert not any(path.startswith(".git/") for path in accepted)
    assert not any(path.startswith("node_modules/") for path in accepted)


def test_scan_excludes_secret_files(sample_repository: Path) -> None:
    result = RepositoryScanner().scan(sample_repository)
    assert reasons(result)[".env"] == "secret file excluded"


def test_scan_skips_binary_and_undecodable_files(sample_repository: Path) -> None:
    skipped = reasons(RepositoryScanner().scan(sample_repository))
    assert skipped["app/blob.py"] == "binary content"
    assert skipped["app/latin.py"] == "invalid utf-8"


def test_scan_does_not_follow_symlinks(sample_repository: Path) -> None:
    link = sample_repository / "app" / "outside.py"
    link.symlink_to("/etc/passwd")
    result = RepositoryScanner().scan(sample_repository)
    assert reasons(result)["app/outside.py"] == "symlink"
    assert "app/outside.py" not in {source.file_path for source in result.files}


def test_scan_does_not_descend_into_symlinked_directories(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    (repository / "src").mkdir(parents=True)
    (repository / "src" / "main.py").write_text("x = 1\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "leak.py").write_text("SECRET = 'leaked'\n", encoding="utf-8")
    os.symlink(outside, repository / "linked")

    result = RepositoryScanner().scan(repository)
    assert all("leak.py" not in source.file_path for source in result.files)


def test_scan_enforces_the_size_limit(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "big.py").write_text("x = 1\n" * 5_000, encoding="utf-8")
    result = RepositoryScanner(ScannerConfig(max_file_bytes=100)).scan(repository)
    assert result.files == []
    assert "exceeds size limit" in reasons(result)["big.py"]


def test_scan_stops_at_the_file_limit(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    for index in range(10):
        (repository / f"mod{index}.py").write_text(f"value = {index}\n", encoding="utf-8")
    result = RepositoryScanner(ScannerConfig(max_files=3)).scan(repository)
    assert len(result.files) == 3
    assert result.truncated is True


def test_scan_computes_content_hashes(sample_repository: Path) -> None:
    result = RepositoryScanner().scan(sample_repository)
    source = next(item for item in result.files if item.file_path == "app/auth.py")
    assert len(source.sha256) == 64
    assert source.language is Language.PYTHON
    assert source.size_bytes > 0


def test_scan_rejects_a_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(NotADirectoryError):
        RepositoryScanner().scan(tmp_path / "does-not-exist")


def test_classify_maps_every_supported_extension() -> None:
    assert classify("a.py") is Language.PYTHON
    assert classify("a.cpp") is Language.CPP
    assert classify("a.h") is Language.C
    assert classify("a.java") is Language.JAVA
    assert classify("a.tsx") is Language.TSX
    assert classify("a.unknown") is Language.UNKNOWN


def test_is_secret_file_detects_credential_material() -> None:
    assert is_secret_file(".env")
    assert is_secret_file(".env.production")
    assert is_secret_file("server.pem")
    assert is_secret_file("id_rsa")
    assert not is_secret_file("main.py")


def test_looks_binary_only_inspects_the_probe_window() -> None:
    assert looks_binary(b"abc\x00def")
    assert not looks_binary(b"plain text")
    assert not looks_binary(b"a" * 9000 + b"\x00")
