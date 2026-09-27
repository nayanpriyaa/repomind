"""Deterministic identifier generation.

Chunk IDs are UUIDv5 values derived from the chunk's structural coordinates.
Two properties matter:

* **Deterministic** - re-indexing an unchanged function produces the same ID, so
  upserts replace rather than duplicate, and SQLite state stays consistent with
  Qdrant without a shared transaction.
* **UUID-shaped** - Qdrant only accepts unsigned integers or UUIDs as point IDs,
  so a raw hash string would be rejected.
"""

from __future__ import annotations

import uuid

NAMESPACE = uuid.UUID("6f6d1c6b-6a0f-5a6a-9c2a-2f0a6b1d8e11")
"""Fixed application namespace. Changing it invalidates every existing ID."""


def chunk_id(
    repository_path: str,
    file_path: str,
    chunk_type: str,
    symbol: str,
    start_line: int,
    end_line: int,
) -> str:
    """Build the stable identifier for a chunk.

    The line range is part of the key on purpose: when a function moves, the old
    point is removed by the file-level delete that precedes re-indexing, and the
    moved function is inserted under a new ID. That is cheaper and far less
    error-prone than trying to diff symbols across revisions.
    """
    key = "\u0000".join(
        (
            repository_path,
            file_path,
            chunk_type,
            symbol,
            str(start_line),
            str(end_line),
        )
    )
    return str(uuid.uuid5(NAMESPACE, key))


def repository_key(repository_path: str) -> str:
    """Normalised key used for repository-scoped filters and bookkeeping."""
    return repository_path.rstrip("/") or "/"
