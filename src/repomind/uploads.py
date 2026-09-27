"""Managed repository storage for browser uploads.

The API accepts a ZIP archive and this module turns it into a directory under
``REPOSITORIES_ROOT`` that the existing scanner/ingestion pipeline can index
unchanged. Filesystem paths never leave the backend: callers address
repositories by a slug ID derived from the archive name.

Extraction is the dangerous part, so it is done entry by entry rather than with
``ZipFile.extractall``:

* every member name is normalised and checked to land inside the destination,
  which blocks Zip Slip (``../../etc/cron.d/x``) and absolute member names;
* symlink members are dropped, so an archive cannot plant a link that later
  escapes the root when the scanner follows it (the scanner refuses symlinks
  too, but defence in depth is cheap here);
* entry count, total uncompressed size and compression ratio are capped, which
  bounds both disk usage and zip-bomb amplification.

Extraction happens into a temporary directory inside the root and is moved into
place only on success, so a rejected or failed archive never leaves a
half-written repository behind.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import stat
import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterable

logger = logging.getLogger(__name__)

TEMP_DIRECTORY_NAME = ".uploads-tmp"
MAX_ID_LENGTH = 64
_ID_ALLOWED = re.compile(r"[^a-z0-9._-]+")
_ID_VALID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_COPY_CHUNK = 1 << 16


class RepositoryUploadError(ValueError):
    """Client-side problem with an upload: bad name, bad archive, too large."""


class RepositoryExistsError(RepositoryUploadError):
    """A repository with the requested ID is already stored."""


class RepositoryNotFoundError(RepositoryUploadError):
    """No stored repository has the requested ID."""


@dataclass(frozen=True, slots=True)
class StoredRepository:
    """A repository directory managed by RepoMind."""

    repository_id: str
    name: str
    path: Path
    """Internal only. Never serialised into an API response."""

    file_count: int
    size_bytes: int
    created_at: float


def normalize_repository_id(raw: str) -> str:
    """Turn a filename or user-supplied name into a safe directory slug.

    Path separators, traversal segments and anything outside
    ``[a-z0-9._-]`` are collapsed, so the result can never be anything but a
    single harmless path segment.
    """
    candidate = PurePosixPath(raw.replace("\\", "/")).name
    if candidate.lower().endswith(".zip"):
        candidate = candidate[: -len(".zip")]
    candidate = _ID_ALLOWED.sub("-", candidate.strip().lower()).strip("-._")
    candidate = re.sub(r"-{2,}", "-", candidate)[:MAX_ID_LENGTH].strip("-._")
    if not candidate or not _ID_VALID.match(candidate):
        raise RepositoryUploadError(
            "repository name must contain at least one letter or digit"
        )
    return candidate


class RepositoryStore:
    """Creates, lists and deletes repository directories under the root."""

    def __init__(
        self,
        root: Path,
        max_archive_bytes: int = 200 * 1024 * 1024,
        max_extracted_bytes: int = 1024 * 1024 * 1024,
        max_entries: int = 20_000,
        max_compression_ratio: int = 200,
    ) -> None:
        self._root = Path(root)
        self._max_archive_bytes = max_archive_bytes
        self._max_extracted_bytes = max_extracted_bytes
        self._max_entries = max_entries
        self._max_compression_ratio = max_compression_ratio

    @property
    def root(self) -> Path:
        return self._root

    def initialize(self) -> None:
        """Create the storage root. Safe to call repeatedly."""
        self._root.mkdir(parents=True, exist_ok=True)
        self._temp_root().mkdir(parents=True, exist_ok=True)

    # -- reads ------------------------------------------------------------ #

    def exists(self, repository_id: str) -> bool:
        return (self._root / normalize_repository_id(repository_id)).is_dir()

    def path_for(self, repository_id: str) -> Path:
        """Resolve an ID to its directory, or raise if it is not stored."""
        path = self._root / normalize_repository_id(repository_id)
        if not path.is_dir():
            raise RepositoryNotFoundError("no such repository")
        return path

    def list(self) -> list[StoredRepository]:
        """Every stored repository, cheapest-first metadata only."""
        if not self._root.is_dir():
            return []
        found: list[StoredRepository] = []
        for entry in sorted(self._root.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            if entry.is_symlink():
                continue
            found.append(self._describe(entry))
        return found

    def describe(self, repository_id: str) -> StoredRepository:
        return self._describe(self.path_for(repository_id))

    # -- writes ----------------------------------------------------------- #

    def create_from_zip(
        self,
        stream: BinaryIO,
        filename: str,
        repository_id: str | None = None,
        overwrite: bool = False,
    ) -> StoredRepository:
        """Store an uploaded ZIP as a new repository directory.

        ``stream`` is consumed once and capped at ``max_archive_bytes``.
        """
        identifier = normalize_repository_id(repository_id or filename)
        destination = self._root / identifier
        if destination.exists() and not overwrite:
            raise RepositoryExistsError(
                f"a repository named {identifier!r} already exists"
            )

        self.initialize()
        staging = self._temp_root() / f"stage-{uuid.uuid4().hex}"
        staging.mkdir(parents=True)
        archive_path = staging / "upload.zip"
        extracted = staging / "content"
        extracted.mkdir()

        try:
            self._spool(stream, archive_path)
            if not zipfile.is_zipfile(archive_path):
                raise RepositoryUploadError("the uploaded file is not a valid ZIP archive")
            with zipfile.ZipFile(archive_path) as archive:
                self._check_manifest(archive)
                self._extract(archive, extracted)

            source = _collapse_single_root(extracted, identifier)
            if not _contains_a_file(source):
                raise RepositoryUploadError("the archive contains no usable files")

            if destination.exists():
                shutil.rmtree(destination)
            os.replace(source, destination)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        logger.info("stored uploaded repository %s", identifier)
        return self._describe(destination)

    def delete(self, repository_id: str) -> None:
        """Remove a stored repository from disk."""
        shutil.rmtree(self.path_for(repository_id))

    # -- internals -------------------------------------------------------- #

    def _temp_root(self) -> Path:
        return self._root / TEMP_DIRECTORY_NAME

    def _spool(self, stream: BinaryIO, target: Path) -> None:
        """Copy the upload to disk, refusing anything over the size cap."""
        written = 0
        with open(target, "wb") as handle:
            while True:
                block = stream.read(_COPY_CHUNK)
                if not block:
                    break
                written += len(block)
                if written > self._max_archive_bytes:
                    raise RepositoryUploadError(
                        f"upload exceeds the {self._max_archive_bytes // (1024 * 1024)} MB limit"
                    )
                handle.write(block)
        if written == 0:
            raise RepositoryUploadError("the uploaded file is empty")

    def _check_manifest(self, archive: zipfile.ZipFile) -> None:
        """Reject bombs before writing a single byte of content."""
        entries = archive.infolist()
        if len(entries) > self._max_entries:
            raise RepositoryUploadError(
                f"archive holds more than {self._max_entries} entries"
            )
        uncompressed = sum(entry.file_size for entry in entries)
        compressed = sum(entry.compress_size for entry in entries) or 1
        if uncompressed > self._max_extracted_bytes:
            raise RepositoryUploadError(
                f"archive expands to more than "
                f"{self._max_extracted_bytes // (1024 * 1024)} MB"
            )
        if uncompressed // compressed > self._max_compression_ratio:
            raise RepositoryUploadError("archive compression ratio looks like a zip bomb")

    def _extract(self, archive: zipfile.ZipFile, destination: Path) -> None:
        """Extract members one at a time, refusing anything unsafe."""
        root = destination.resolve()
        written = 0

        for entry in archive.infolist():
            if _is_symlink(entry):
                logger.info("skipping symlink member %s", entry.filename)
                continue

            relative = _safe_member_path(entry.filename)
            if relative is None:
                raise RepositoryUploadError(
                    "archive contains an unsafe path and was rejected"
                )
            if not relative.parts:
                continue

            target = (root / relative).resolve()
            if target != root and root not in target.parents:
                raise RepositoryUploadError(
                    "archive contains an unsafe path and was rejected"
                )

            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source, open(target, "wb") as sink:
                while True:
                    block = source.read(_COPY_CHUNK)
                    if not block:
                        break
                    written += len(block)
                    if written > self._max_extracted_bytes:
                        raise RepositoryUploadError(
                            "archive expands beyond the configured size limit"
                        )
                    sink.write(block)
            os.chmod(target, 0o644)

    @staticmethod
    def _describe(path: Path) -> StoredRepository:
        file_count = 0
        size_bytes = 0
        for current, directories, files in os.walk(path, followlinks=False):
            directories[:] = [name for name in directories if name != ".git"]
            for name in files:
                file_path = Path(current) / name
                if file_path.is_symlink():
                    continue
                try:
                    size_bytes += file_path.stat().st_size
                except OSError:  # pragma: no cover - racing deletes
                    continue
                file_count += 1
        try:
            created_at = path.stat().st_mtime
        except OSError:  # pragma: no cover
            created_at = time.time()
        return StoredRepository(
            repository_id=path.name,
            name=path.name,
            path=path,
            file_count=file_count,
            size_bytes=size_bytes,
            created_at=created_at,
        )


def _contains_a_file(root: Path) -> bool:
    """True when the tree holds at least one regular file, at any depth."""
    for _, _, files in os.walk(root, followlinks=False):
        if files:
            return True
    return False


def _safe_member_path(name: str) -> PurePosixPath | None:
    """Normalise a ZIP member name, or return ``None`` if it is unsafe."""
    normalized = name.replace("\\", "/")
    candidate = PurePosixPath(normalized)
    if candidate.is_absolute() or normalized.startswith("/"):
        return None
    if re.match(r"^[a-zA-Z]:", normalized):  # Windows drive-absolute member
        return None
    parts = [part for part in candidate.parts if part not in ("", ".")]
    if any(part == ".." for part in parts):
        return None
    return PurePosixPath(*parts) if parts else PurePosixPath()


def _is_symlink(entry: zipfile.ZipInfo) -> bool:
    """ZIP stores the unix mode in the top 16 bits of ``external_attr``."""
    return stat.S_ISLNK(entry.external_attr >> 16)


_ROOT_MARKERS = frozenset(
    {
        "readme",
        "readme.md",
        "readme.rst",
        "readme.txt",
        ".gitignore",
        ".git",
        "license",
        "license.md",
        "package.json",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "requirements.txt",
        "go.mod",
        "cargo.toml",
        "pom.xml",
        "build.gradle",
        "makefile",
        "dockerfile",
        "tsconfig.json",
        "composer.json",
        "gemfile",
        "src",
    }
)

_VERSION_SUFFIX = re.compile(r"-(main|master|develop|trunk|v?\d+(\.\d+)*)$")


def _collapse_single_root(extracted: Path, archive_stem: str) -> Path:
    """Unwrap ``project-main/`` wrappers that archive tools add.

    Collapsing unconditionally is wrong: a ZIP whose only top-level entry is a
    genuine source package (``app/``) would lose that path segment, and every
    citation would then point at the wrong location. A directory is treated as a
    wrapper only when its name matches the archive name (GitHub's
    ``repo-main.zip`` → ``repo-main/``, "compress this folder" → ``Project/``)
    or when it holds a recognisable project-root marker.
    """
    children = [child for child in extracted.iterdir() if child.name != "__MACOSX"]
    if len(children) != 1:
        return extracted
    child = children[0]
    if not child.is_dir() or child.is_symlink():
        return extracted
    return child if _looks_like_wrapper(child, archive_stem) else extracted


def _looks_like_wrapper(child: Path, archive_stem: str) -> bool:
    normalized = _ID_ALLOWED.sub("-", child.name.strip().lower()).strip("-._")
    base = _VERSION_SUFFIX.sub("", normalized)
    if archive_stem and archive_stem in {normalized, base}:
        return True
    try:
        names = {entry.name.lower() for entry in child.iterdir()}
    except OSError:  # pragma: no cover - defensive
        return False
    return bool(names & _ROOT_MARKERS)


def iter_repository_ids(repositories: Iterable[StoredRepository]) -> list[str]:
    """Convenience used by the API when merging store and index state."""
    return [repository.repository_id for repository in repositories]
