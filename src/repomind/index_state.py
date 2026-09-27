"""SQLite-backed indexing state.

This is the source of truth for *what is currently indexed*: file digests, the
chunks each file produced, and per-repository totals. Comparing a fresh scan
against it yields the new/modified/unchanged/deleted partition that drives
incremental indexing.

Connections are opened per operation rather than held open. SQLite in WAL mode
handles that cheaply, and it sidesteps the thread-affinity problems that a
long-lived connection causes under a threaded ASGI server.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence

from .models import CodeChunk, FileDiff, RepositoryStatus, SourceFile

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS repositories (
    repository_path  TEXT PRIMARY KEY,
    last_indexed_at  REAL,
    file_count       INTEGER NOT NULL DEFAULT 0,
    chunk_count      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS files (
    repository_path  TEXT NOT NULL,
    file_path        TEXT NOT NULL,
    sha256           TEXT NOT NULL,
    size_bytes       INTEGER NOT NULL,
    language         TEXT NOT NULL,
    chunk_count      INTEGER NOT NULL DEFAULT 0,
    indexed_at       REAL NOT NULL,
    PRIMARY KEY (repository_path, file_path)
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id         TEXT PRIMARY KEY,
    repository_path  TEXT NOT NULL,
    file_path        TEXT NOT NULL,
    language         TEXT NOT NULL,
    chunk_type       TEXT NOT NULL,
    symbol           TEXT NOT NULL,
    start_line       INTEGER NOT NULL,
    end_line         INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_file
    ON chunks (repository_path, file_path);
CREATE INDEX IF NOT EXISTS idx_files_repo
    ON files (repository_path);
"""


@contextmanager
def connect(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    """Open a tuned SQLite connection, committing on success."""
    path = Path(db_path)
    if path.parent and str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30.0)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout=30000")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


class IndexState:
    """Persistent record of indexed files and chunks."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    @property
    def db_path(self) -> Path:
        return self._db_path

    def initialize(self) -> None:
        """Create the schema if needed. Safe to call repeatedly."""
        with connect(self._db_path) as connection:
            connection.executescript(_SCHEMA)
            row = connection.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
                )

    # -- diffing ---------------------------------------------------------- #

    def known_hashes(self, repository_path: str) -> dict[str, str]:
        """Map of ``file_path -> sha256`` currently recorded for a repository."""
        with connect(self._db_path) as connection:
            rows = connection.execute(
                "SELECT file_path, sha256 FROM files WHERE repository_path = ?",
                (repository_path,),
            ).fetchall()
        return {row["file_path"]: row["sha256"] for row in rows}

    def diff(
        self, repository_path: str, scanned: Sequence[SourceFile]
    ) -> FileDiff:
        """Partition ``scanned`` into new/modified/unchanged plus deleted paths."""
        known = self.known_hashes(repository_path)
        new: list[str] = []
        modified: list[str] = []
        unchanged: list[str] = []

        for source in scanned:
            previous = known.pop(source.file_path, None)
            if previous is None:
                new.append(source.file_path)
            elif previous != source.sha256:
                modified.append(source.file_path)
            else:
                unchanged.append(source.file_path)

        return FileDiff(
            new=new,
            modified=modified,
            unchanged=unchanged,
            deleted=sorted(known),
        )

    # -- writes ----------------------------------------------------------- #

    def record_file(self, source: SourceFile, chunks: Sequence[CodeChunk]) -> None:
        """Persist a file's digest and replace its chunk rows atomically."""
        now = time.time()
        with connect(self._db_path) as connection:
            connection.execute(
                "DELETE FROM chunks WHERE repository_path = ? AND file_path = ?",
                (source.repository_path, source.file_path),
            )
            connection.executemany(
                """
                INSERT OR REPLACE INTO chunks (
                    chunk_id, repository_path, file_path, language,
                    chunk_type, symbol, start_line, end_line
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.chunk_id,
                        chunk.repository_path,
                        chunk.file_path,
                        chunk.language.value,
                        chunk.chunk_type.value,
                        chunk.symbol,
                        chunk.start_line,
                        chunk.end_line,
                    )
                    for chunk in chunks
                ],
            )
            connection.execute(
                """
                INSERT INTO files (
                    repository_path, file_path, sha256, size_bytes,
                    language, chunk_count, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (repository_path, file_path) DO UPDATE SET
                    sha256      = excluded.sha256,
                    size_bytes  = excluded.size_bytes,
                    language    = excluded.language,
                    chunk_count = excluded.chunk_count,
                    indexed_at  = excluded.indexed_at
                """,
                (
                    source.repository_path,
                    source.file_path,
                    source.sha256,
                    source.size_bytes,
                    source.language.value,
                    len(chunks),
                    now,
                ),
            )

    def chunk_ids_for_file(self, repository_path: str, file_path: str) -> list[str]:
        """IDs of every chunk currently attributed to one file."""
        with connect(self._db_path) as connection:
            rows = connection.execute(
                "SELECT chunk_id FROM chunks WHERE repository_path = ? AND file_path = ?",
                (repository_path, file_path),
            ).fetchall()
        return [row["chunk_id"] for row in rows]

    def delete_file(self, repository_path: str, file_path: str) -> int:
        """Forget one file. Returns the number of chunk rows removed."""
        with connect(self._db_path) as connection:
            cursor = connection.execute(
                "DELETE FROM chunks WHERE repository_path = ? AND file_path = ?",
                (repository_path, file_path),
            )
            removed = cursor.rowcount or 0
            connection.execute(
                "DELETE FROM files WHERE repository_path = ? AND file_path = ?",
                (repository_path, file_path),
            )
        return removed

    def delete_repository(self, repository_path: str) -> int:
        """Forget an entire repository. Returns the number of chunk rows removed."""
        with connect(self._db_path) as connection:
            cursor = connection.execute(
                "DELETE FROM chunks WHERE repository_path = ?", (repository_path,)
            )
            removed = cursor.rowcount or 0
            connection.execute(
                "DELETE FROM files WHERE repository_path = ?", (repository_path,)
            )
            connection.execute(
                "DELETE FROM repositories WHERE repository_path = ?", (repository_path,)
            )
        return removed

    def touch_repository(self, repository_path: str) -> None:
        """Refresh a repository's aggregate counters and timestamp."""
        with connect(self._db_path) as connection:
            file_count = connection.execute(
                "SELECT COUNT(*) AS n FROM files WHERE repository_path = ?",
                (repository_path,),
            ).fetchone()["n"]
            chunk_count = connection.execute(
                "SELECT COUNT(*) AS n FROM chunks WHERE repository_path = ?",
                (repository_path,),
            ).fetchone()["n"]
            connection.execute(
                """
                INSERT INTO repositories (
                    repository_path, last_indexed_at, file_count, chunk_count
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT (repository_path) DO UPDATE SET
                    last_indexed_at = excluded.last_indexed_at,
                    file_count      = excluded.file_count,
                    chunk_count     = excluded.chunk_count
                """,
                (repository_path, time.time(), file_count, chunk_count),
            )

    # -- reads ------------------------------------------------------------ #

    def status(self, repository_path: str) -> RepositoryStatus:
        """Current indexing status for one repository."""
        with connect(self._db_path) as connection:
            row = connection.execute(
                "SELECT * FROM repositories WHERE repository_path = ?",
                (repository_path,),
            ).fetchone()
            languages = {
                item["language"]: item["n"]
                for item in connection.execute(
                    """
                    SELECT language, COUNT(*) AS n FROM files
                    WHERE repository_path = ? GROUP BY language
                    """,
                    (repository_path,),
                ).fetchall()
            }
        if row is None:
            return RepositoryStatus(
                repository_path=repository_path,
                indexed=False,
                file_count=0,
                chunk_count=0,
                last_indexed_at=None,
            )
        return RepositoryStatus(
            repository_path=repository_path,
            indexed=row["file_count"] > 0,
            file_count=row["file_count"],
            chunk_count=row["chunk_count"],
            last_indexed_at=row["last_indexed_at"],
            languages=languages,
        )

    def list_repositories(self) -> list[RepositoryStatus]:
        """Status for every repository RepoMind has indexed."""
        with connect(self._db_path) as connection:
            rows = connection.execute(
                "SELECT repository_path FROM repositories ORDER BY repository_path"
            ).fetchall()
        return [self.status(row["repository_path"]) for row in rows]

    def health_check(self) -> bool:
        """Cheap liveness probe used by ``GET /ready``."""
        try:
            with connect(self._db_path) as connection:
                connection.execute("SELECT 1 FROM schema_version").fetchone()
            return True
        except sqlite3.Error:  # pragma: no cover - defensive
            logger.debug("sqlite health check failed", exc_info=True)
            return False
