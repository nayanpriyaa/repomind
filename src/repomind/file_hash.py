"""SHA-256 helpers used for incremental indexing.

Hashing content (not mtime/size) is what makes re-indexing idempotent: a file
that is touched but unchanged produces the same digest and is skipped, and a
file restored to a previous state is correctly recognised as unchanged.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_READ_CHUNK_BYTES = 65_536


def hash_bytes(data: bytes) -> str:
    """Return the hex SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    """Return the hex SHA-256 digest of ``text`` encoded as UTF-8."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_file(path: str | Path) -> str:
    """Stream ``path`` and return its hex SHA-256 digest.

    Streams in fixed-size blocks so that hashing never materialises a large file
    in memory.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(_READ_CHUNK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()
