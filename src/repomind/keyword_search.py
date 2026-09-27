"""Lexical search over indexed chunks using SQLite FTS5 with BM25 ranking.

Why lexical search at all, given a vector index? Because embeddings are bad at
exact identifiers. A query for ``AuthMiddleware`` or ``ERR_TOKEN_EXPIRED`` should
return the literal definition, and BM25 does that reliably while dense retrieval
often returns "something about authentication". Hybrid retrieval exists to get
both behaviours.

Implementation notes
--------------------
* The FTS5 table carries the payload as ``UNINDEXED`` columns, so a keyword hit
  is self-contained and needs no join to render a citation.
* Column weights favour symbol names over raw content, then file paths.
* User input is never interpolated into the MATCH expression. Terms are
  extracted with a whitelist regex and re-quoted, which makes FTS5 operator
  injection (``NEAR``, ``*``, ``"``) impossible.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .index_state import connect
from .models import CodeChunk

logger = logging.getLogger(__name__)

_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    symbol,
    file_path,
    content,
    symbol_display UNINDEXED,
    chunk_id UNINDEXED,
    repository_path UNINDEXED,
    language UNINDEXED,
    chunk_type UNINDEXED,
    start_line UNINDEXED,
    end_line UNINDEXED,
    tokenize = "unicode61 remove_diacritics 2 tokenchars '_'"
);
"""

# bm25() weights, positional per indexed column: symbol, file_path, content.
_BM25_WEIGHTS = (6.0, 2.0, 1.0)

_TERM_PATTERN = re.compile(r"[A-Za-z0-9_]+")
_CAMEL_PATTERN = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_MAX_TERMS = 32


@dataclass(frozen=True, slots=True)
class KeywordHit:
    """A lexical match with everything needed to build a citation."""

    chunk_id: str
    score: float
    repository_path: str
    file_path: str
    language: str
    chunk_type: str
    symbol: str
    start_line: int
    end_line: int
    content: str


class KeywordIndex:
    """FTS5 index over chunk text, symbols and paths."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def initialize(self) -> None:
        """Create the virtual table if needed. Safe to call repeatedly."""
        with connect(self._db_path) as connection:
            connection.executescript(_FTS_SCHEMA)

    def index_chunks(self, chunks: Sequence[CodeChunk]) -> int:
        """Insert chunks. Callers must delete the file's rows first."""
        if not chunks:
            return 0
        with connect(self._db_path) as connection:
            connection.executemany(
                """
                INSERT INTO chunks_fts (
                    symbol, file_path, content, symbol_display, chunk_id,
                    repository_path, language, chunk_type, start_line, end_line
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        _expand_symbol(chunk.symbol),
                        chunk.file_path,
                        chunk.content,
                        chunk.symbol,
                        chunk.chunk_id,
                        chunk.repository_path,
                        chunk.language.value,
                        chunk.chunk_type.value,
                        chunk.start_line,
                        chunk.end_line,
                    )
                    for chunk in chunks
                ],
            )
        return len(chunks)

    def delete_file(self, repository_path: str, file_path: str) -> None:
        with connect(self._db_path) as connection:
            connection.execute(
                "DELETE FROM chunks_fts WHERE repository_path = ? AND file_path = ?",
                (repository_path, file_path),
            )

    def delete_repository(self, repository_path: str) -> None:
        with connect(self._db_path) as connection:
            connection.execute(
                "DELETE FROM chunks_fts WHERE repository_path = ?", (repository_path,)
            )

    def count(self, repository_path: str | None = None) -> int:
        with connect(self._db_path) as connection:
            if repository_path is None:
                row = connection.execute("SELECT COUNT(*) AS n FROM chunks_fts").fetchone()
            else:
                row = connection.execute(
                    "SELECT COUNT(*) AS n FROM chunks_fts WHERE repository_path = ?",
                    (repository_path,),
                ).fetchone()
        return int(row["n"])

    def search(
        self,
        query: str,
        top_k: int = 10,
        repository_path: str | None = None,
    ) -> list[KeywordHit]:
        """Return the ``top_k`` best BM25 matches for ``query``."""
        match_expression = build_match_expression(query)
        if not match_expression:
            return []

        sql = [
            "SELECT chunk_id, repository_path, file_path, language, chunk_type,",
            "       symbol_display, start_line, end_line, content,",
            f"       bm25(chunks_fts, {', '.join(str(w) for w in _BM25_WEIGHTS)}) AS rank",
            "FROM chunks_fts WHERE chunks_fts MATCH ?",
        ]
        parameters: list[Any] = [match_expression]
        if repository_path is not None:
            sql.append("AND repository_path = ?")
            parameters.append(repository_path)
        sql.append("ORDER BY rank LIMIT ?")
        parameters.append(top_k)

        with connect(self._db_path) as connection:
            try:
                rows = connection.execute("\n".join(sql), parameters).fetchall()
            except Exception:  # noqa: BLE001 - malformed MATCH must not 500
                logger.warning("FTS query failed for %r", query, exc_info=True)
                return []

        # bm25() returns more-negative values for better matches; flip the sign
        # so that callers can treat every backend as "higher is better".
        return [
            KeywordHit(
                chunk_id=row["chunk_id"],
                score=-float(row["rank"]),
                repository_path=row["repository_path"],
                file_path=row["file_path"],
                language=row["language"],
                chunk_type=row["chunk_type"],
                symbol=row["symbol_display"],
                start_line=int(row["start_line"]),
                end_line=int(row["end_line"]),
                content=row["content"],
            )
            for row in rows
        ]

    def health_check(self) -> bool:
        try:
            self.count()
            return True
        except Exception:  # noqa: BLE001
            logger.debug("keyword index health check failed", exc_info=True)
            return False


def build_match_expression(query: str) -> str:
    """Turn free text into a safe FTS5 ``MATCH`` expression.

    Terms are OR-ed rather than AND-ed: natural-language questions carry filler
    words that would otherwise force zero results, and BM25 already rewards
    documents matching more of the query.
    """
    terms: list[str] = []
    seen: set[str] = set()
    for raw in _TERM_PATTERN.findall(query):
        for term in _split_identifier(raw):
            lowered = term.lower()
            if len(lowered) < 2 or lowered in seen:
                continue
            seen.add(lowered)
            terms.append(lowered)
            if len(terms) >= _MAX_TERMS:
                break
    return " OR ".join(f'"{term}"' for term in terms)


def _split_identifier(token: str) -> list[str]:
    """Yield the token plus its camelCase/snake_case components."""
    parts = [token]
    for piece in _CAMEL_PATTERN.split(token):
        parts.extend(piece.split("_"))
    return [part for part in parts if part]


def _expand_symbol(symbol: str) -> str:
    """Index ``getUserToken`` as ``getUserToken get User Token`` so both match.

    The original symbol is stored separately in ``symbol_display`` and is what
    citations render; only the searchable column is expanded.
    """
    return " ".join(dict.fromkeys([symbol, *_split_identifier(symbol)]))
