"""Safe recursive repository scanning.

The scanner is the trust boundary between an arbitrary directory on disk and the
rest of the pipeline. Everything it emits is guaranteed to be: inside the
repository root, a regular file (never a symlink), below the size limit, valid
UTF-8 text, and not a recognised secret file.

A single unreadable or malformed file must never abort a scan, so every per-file
failure is captured as a :class:`SkippedFile` and reported alongside the results.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from .file_hash import hash_bytes
from .models import Language, SkippedFile, SourceFile

logger = logging.getLogger(__name__)

EXTENSION_LANGUAGES: dict[str, Language] = {
    ".py": Language.PYTHON,
    ".pyi": Language.PYTHON,
    ".c": Language.C,
    ".h": Language.C,
    ".cpp": Language.CPP,
    ".cc": Language.CPP,
    ".cxx": Language.CPP,
    ".hpp": Language.CPP,
    ".hh": Language.CPP,
    ".java": Language.JAVA,
    ".js": Language.JAVASCRIPT,
    ".jsx": Language.JAVASCRIPT,
    ".mjs": Language.JAVASCRIPT,
    ".cjs": Language.JAVASCRIPT,
    ".ts": Language.TYPESCRIPT,
    ".mts": Language.TYPESCRIPT,
    ".tsx": Language.TSX,
    ".md": Language.MARKDOWN,
    ".markdown": Language.MARKDOWN,
    ".json": Language.JSON,
    ".yaml": Language.YAML,
    ".yml": Language.YAML,
    ".toml": Language.TOML,
}

IGNORED_DIRECTORIES: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "node_modules",
        "bower_components",
        "build",
        "dist",
        "out",
        "target",
        "bin",
        "obj",
        ".next",
        ".nuxt",
        ".gradle",
        ".idea",
        ".vscode",
        "coverage",
        "htmlcov",
        ".cache",
        "site-packages",
        "vendor",
        ".terraform",
    }
)

SECRET_FILENAMES: frozenset[str] = frozenset(
    {
        ".env",
        ".netrc",
        ".npmrc",
        ".pypirc",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "credentials",
        "credentials.json",
        "service-account.json",
        "secrets.json",
        "secrets.yaml",
        "secrets.yml",
    }
)

SECRET_SUFFIXES: tuple[str, ...] = (
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".jks",
    ".keystore",
    ".crt",
    ".der",
)

_BINARY_PROBE_BYTES = 8192


@dataclass(frozen=True, slots=True)
class ScannerConfig:
    """Tunable scanner limits."""

    max_file_bytes: int = 1_048_576
    max_files: int = 20_000
    ignored_directories: frozenset[str] = IGNORED_DIRECTORIES
    include_documents: bool = True


@dataclass(slots=True)
class ScanResult:
    """Files accepted by the scanner plus an audit trail of what was skipped."""

    files: list[SourceFile] = field(default_factory=list)
    skipped: list[SkippedFile] = field(default_factory=list)
    truncated: bool = False

    @property
    def file_paths(self) -> set[str]:
        return {source.file_path for source in self.files}


def classify(path: str | Path) -> Language:
    """Map a filename to a :class:`Language` (``UNKNOWN`` when unsupported)."""
    return EXTENSION_LANGUAGES.get(Path(path).suffix.lower(), Language.UNKNOWN)


def is_secret_file(name: str) -> bool:
    """Heuristically detect credential material that must never be indexed."""
    lowered = name.lower()
    if lowered in SECRET_FILENAMES or lowered.startswith(".env"):
        return True
    return lowered.endswith(SECRET_SUFFIXES)


def looks_binary(data: bytes) -> bool:
    """Treat a NUL byte in the leading probe window as proof of binary content."""
    return b"\x00" in data[:_BINARY_PROBE_BYTES]


class RepositoryScanner:
    """Walks a repository and yields decodable, in-scope source files."""

    def __init__(self, config: ScannerConfig | None = None) -> None:
        self._config = config or ScannerConfig()

    @property
    def config(self) -> ScannerConfig:
        return self._config

    def scan(self, repository_path: str | Path) -> ScanResult:
        """Scan ``repository_path`` and return accepted plus skipped files."""
        root = Path(repository_path).resolve()
        if not root.is_dir():
            raise NotADirectoryError(f"not a directory: {root}")

        result = ScanResult()
        for absolute in self._walk(root, result):
            if len(result.files) >= self._config.max_files:
                result.truncated = True
                logger.warning(
                    "file limit of %d reached while scanning %s",
                    self._config.max_files,
                    root,
                )
                break
            source = self._read_file(root, absolute, result)
            if source is not None:
                result.files.append(source)
        return result

    def _walk(self, root: Path, result: ScanResult) -> Iterator[Path]:
        """Yield candidate file paths, pruning ignored and unsafe directories."""
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            current = Path(dirpath)
            dirnames[:] = [
                name
                for name in dirnames
                if name not in self._config.ignored_directories
                and not self._is_symlink(current / name)
            ]
            for filename in sorted(filenames):
                yield current / filename

    @staticmethod
    def _is_symlink(path: Path) -> bool:
        try:
            return path.is_symlink()
        except OSError:  # pragma: no cover - defensive
            return True

    def _read_file(
        self, root: Path, absolute: Path, result: ScanResult
    ) -> SourceFile | None:
        """Validate and read one file, recording a skip reason on rejection."""
        try:
            relative = absolute.relative_to(root).as_posix()
        except ValueError:  # pragma: no cover - os.walk stays under root
            return None

        def skip(reason: str) -> None:
            result.skipped.append(SkippedFile(file_path=relative, reason=reason))

        if absolute.is_symlink():
            skip("symlink")
            return None
        if is_secret_file(absolute.name):
            skip("secret file excluded")
            return None

        language = classify(absolute)
        if language is Language.UNKNOWN:
            return None
        if not language.is_code and not self._config.include_documents:
            return None

        try:
            stat = absolute.stat()
        except OSError as exc:
            skip(f"stat failed: {exc.__class__.__name__}")
            return None
        if not os.path.isfile(absolute):
            skip("not a regular file")
            return None
        if stat.st_size > self._config.max_file_bytes:
            skip(f"exceeds size limit ({stat.st_size} bytes)")
            return None
        if stat.st_size == 0:
            skip("empty file")
            return None

        try:
            raw = absolute.read_bytes()
        except OSError as exc:
            skip(f"unreadable: {exc.__class__.__name__}")
            return None

        if looks_binary(raw):
            skip("binary content")
            return None

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            skip("invalid utf-8")
            return None

        return SourceFile(
            repository_path=str(root),
            file_path=relative,
            absolute_path=str(absolute),
            language=language,
            size_bytes=stat.st_size,
            sha256=hash_bytes(raw),
            content=text,
        )
