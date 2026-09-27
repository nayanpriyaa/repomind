"""Configuration loading and the repository-root allowlist."""

from __future__ import annotations

from pathlib import Path

import pytest

from repomind.config import RepositoryAccessError, Settings


def test_settings_read_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("QDRANT_HOST", "qdrant")
    monkeypatch.setenv("QDRANT_PORT", "7777")
    monkeypatch.setenv("GEMINI_API_KEY", "abc123")
    monkeypatch.setenv("REPOSITORIES_ROOT", "/srv/repos")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://a.test, http://b.test")
    settings = Settings.from_env()
    assert settings.qdrant_host == "qdrant"
    assert settings.qdrant_port == 7777
    assert settings.repositories_root == Path("/srv/repos")
    assert settings.cors_allow_origins == ["http://a.test", "http://b.test"]
    assert settings.llm_enabled is True


def test_defaults_apply_when_the_environment_is_empty(monkeypatch) -> None:
    for name in ("QDRANT_HOST", "QDRANT_PORT", "GEMINI_API_KEY", "EMBEDDING_MODEL"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_env()
    assert settings.qdrant_port == 6333
    assert settings.llm_enabled is False


def test_api_key_is_hidden_from_repr() -> None:
    settings = Settings(gemini_api_key="super-secret-value")
    assert "super-secret-value" not in repr(settings)


def test_relative_paths_resolve_inside_the_root(tmp_path: Path) -> None:
    (tmp_path / "demo").mkdir()
    settings = Settings(repositories_root=tmp_path)
    assert settings.resolve_repository_path("demo") == (tmp_path / "demo").resolve()


def test_traversal_escapes_are_rejected(tmp_path: Path) -> None:
    (tmp_path / "demo").mkdir()
    settings = Settings(repositories_root=tmp_path / "demo")
    for hostile in ("../", "../../etc", "demo/../../..", "/etc"):
        with pytest.raises(RepositoryAccessError):
            settings.resolve_repository_path(hostile)


def test_absolute_paths_outside_the_root_are_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "root").mkdir()
    settings = Settings(repositories_root=tmp_path / "root")
    with pytest.raises(RepositoryAccessError):
        settings.resolve_repository_path(str(outside))


def test_symlinked_escapes_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "escape").symlink_to(outside)
    settings = Settings(repositories_root=root)
    with pytest.raises(RepositoryAccessError):
        settings.resolve_repository_path("escape")


def test_missing_directories_are_rejected(tmp_path: Path) -> None:
    settings = Settings(repositories_root=tmp_path)
    with pytest.raises(RepositoryAccessError):
        settings.resolve_repository_path("no-such-repo")


def test_files_are_not_valid_repositories(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    settings = Settings(repositories_root=tmp_path)
    with pytest.raises(RepositoryAccessError):
        settings.resolve_repository_path("a.py")


def test_the_root_itself_is_allowed(tmp_path: Path) -> None:
    settings = Settings(repositories_root=tmp_path)
    assert settings.resolve_repository_path(str(tmp_path)) == tmp_path.resolve()
