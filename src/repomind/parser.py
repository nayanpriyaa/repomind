"""Structural chunking.

This module owns the chunk factory, the Python AST parser, the document chunker
and the language dispatcher. Non-Python languages are delegated to the
tree-sitter backed parsers, which are imported lazily inside :func:`parse_file`
so that importing ``repomind.parser`` never requires tree-sitter to be present.

Design notes
------------
* A class does **not** swallow its methods. The class chunk carries the
  declaration, docstring and class-level attributes; each method becomes its own
  chunk. This avoids storing the same source twice and keeps embeddings focused.
* Module-level code (imports, constants, script bodies) is preserved as
  contiguous ``MODULE`` chunks with real line ranges, so citations stay accurate.
* Fixed-size splitting exists only as a fallback for files that fail to parse.
"""

from __future__ import annotations

import ast
import logging
from typing import Iterable, Sequence

from .ids import chunk_id
from .models import ChunkType, CodeChunk, Language, SourceFile

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHUNK_CHARACTERS = 6_000
_FALLBACK_WINDOW_LINES = 60
_FALLBACK_OVERLAP_LINES = 10
_MIN_CHUNK_CHARACTERS = 12


def make_chunk(
    source: SourceFile,
    chunk_type: ChunkType,
    symbol: str,
    start_line: int,
    end_line: int,
    content: str,
    parent_symbol: str | None = None,
    max_characters: int = DEFAULT_MAX_CHUNK_CHARACTERS,
) -> CodeChunk | None:
    """Build a :class:`CodeChunk` with a deterministic ID, or ``None``.

    Returns ``None`` for chunks that carry no usable signal (whitespace only, or
    shorter than :data:`_MIN_CHUNK_CHARACTERS`). Oversized chunks are truncated
    rather than dropped so that a huge generated function is still findable.
    """
    if not content or not content.strip():
        return None
    if len(content.strip()) < _MIN_CHUNK_CHARACTERS:
        return None
    if len(content) > max_characters:
        content = content[:max_characters] + "\n... [truncated]"
    return CodeChunk(
        chunk_id=chunk_id(
            source.repository_path,
            source.file_path,
            chunk_type.value,
            symbol,
            start_line,
            end_line,
        ),
        repository_path=source.repository_path,
        file_path=source.file_path,
        language=source.language,
        chunk_type=chunk_type,
        symbol=symbol,
        start_line=start_line,
        end_line=end_line,
        content=content,
        parent_symbol=parent_symbol,
    )


def slice_lines(lines: Sequence[str], start_line: int, end_line: int) -> str:
    """Join 1-indexed, inclusive line range ``[start_line, end_line]``."""
    start = max(start_line - 1, 0)
    end = min(end_line, len(lines))
    return "\n".join(lines[start:end])


def parse_file(
    source: SourceFile, max_chunk_characters: int = DEFAULT_MAX_CHUNK_CHARACTERS
) -> list[CodeChunk]:
    """Chunk one scanned file according to its language.

    Never raises for malformed input: a file that cannot be parsed structurally
    degrades to windowed chunking so that its content remains searchable.
    """
    try:
        if source.language is Language.PYTHON:
            return parse_python(source, max_chunk_characters)
        if source.language in (Language.C, Language.CPP):
            from . import cpp_parser

            return cpp_parser.parse(source, max_chunk_characters)
        if source.language is Language.JAVA:
            from . import java_parser

            return java_parser.parse(source, max_chunk_characters)
        if source.language in (
            Language.JAVASCRIPT,
            Language.TYPESCRIPT,
            Language.TSX,
        ):
            from . import javascript_parser

            return javascript_parser.parse(source, max_chunk_characters)
        return parse_document(source, max_chunk_characters)
    except Exception:  # noqa: BLE001 - one bad file must not stop indexing
        logger.warning(
            "structural parsing failed for %s, falling back to windows",
            source.file_path,
            exc_info=True,
        )
        return fallback_chunks(source, max_chunk_characters)


# --------------------------------------------------------------------------- #
# Python
# --------------------------------------------------------------------------- #

_FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


def parse_python(
    source: SourceFile, max_chunk_characters: int = DEFAULT_MAX_CHUNK_CHARACTERS
) -> list[CodeChunk]:
    """Chunk Python using the standard library AST."""
    try:
        tree = ast.parse(source.content, filename=source.file_path)
    except (SyntaxError, ValueError, RecursionError):
        logger.info("python syntax error in %s, using windows", source.file_path)
        return fallback_chunks(source, max_chunk_characters)

    lines = source.content.splitlines()
    chunks: list[CodeChunk] = []
    covered: set[int] = set()

    for node in tree.body:
        if isinstance(node, _FUNCTION_NODES):
            start, end = _node_span(node)
            covered.update(range(start, end + 1))
            _append(
                chunks,
                make_chunk(
                    source,
                    ChunkType.ASYNC_FUNCTION
                    if isinstance(node, ast.AsyncFunctionDef)
                    else ChunkType.FUNCTION,
                    node.name,
                    start,
                    end,
                    slice_lines(lines, start, end),
                    max_characters=max_chunk_characters,
                ),
            )
        elif isinstance(node, ast.ClassDef):
            start, end = _node_span(node)
            covered.update(range(start, end + 1))
            chunks.extend(
                _python_class_chunks(source, node, lines, max_chunk_characters)
            )

    chunks.extend(module_chunks(source, lines, covered, max_chunk_characters))
    return chunks


def _python_class_chunks(
    source: SourceFile,
    node: ast.ClassDef,
    lines: Sequence[str],
    max_chunk_characters: int,
) -> list[CodeChunk]:
    """Emit the class shell as one chunk and every method as its own chunk."""
    chunks: list[CodeChunk] = []
    class_start, class_end = _node_span(node)
    method_spans: list[tuple[int, int]] = []

    for child in node.body:
        if not isinstance(child, _FUNCTION_NODES):
            continue
        start, end = _node_span(child)
        method_spans.append((start, end))
        chunk_type = (
            ChunkType.CONSTRUCTOR
            if child.name in {"__init__", "__new__"}
            else ChunkType.METHOD
        )
        _append(
            chunks,
            make_chunk(
                source,
                chunk_type,
                f"{node.name}.{child.name}",
                start,
                end,
                slice_lines(lines, start, end),
                parent_symbol=node.name,
                max_characters=max_chunk_characters,
            ),
        )

    shell_lines = [
        line_no
        for line_no in range(class_start, class_end + 1)
        if not any(start <= line_no <= end for start, end in method_spans)
    ]
    # Drop trailing blank lines so the reported range ends on real code.
    while shell_lines and not lines[shell_lines[-1] - 1].strip():
        shell_lines.pop()
    if shell_lines:
        shell = "\n".join(lines[line_no - 1] for line_no in shell_lines)
        _append(
            chunks,
            make_chunk(
                source,
                ChunkType.CLASS,
                node.name,
                class_start,
                shell_lines[-1],
                shell,
                max_characters=max_chunk_characters,
            ),
        )
    return chunks


def module_chunks(
    source: SourceFile,
    lines: Sequence[str],
    covered: set[int],
    max_chunk_characters: int = DEFAULT_MAX_CHUNK_CHARACTERS,
) -> list[CodeChunk]:
    """Turn contiguous runs of uncovered lines into ``MODULE`` chunks.

    Shared by the Python parser and the tree-sitter parsers so that top-level
    code (imports, includes, globals, script bodies) is never lost, and so the
    two backends cannot drift apart.
    """
    chunks: list[CodeChunk] = []
    run: list[int] = []

    def flush() -> None:
        if not run:
            return
        start, end = run[0], run[-1]
        body = slice_lines(lines, start, end)
        _append(
            chunks,
            make_chunk(
                source,
                ChunkType.MODULE,
                f"{source.file_path}:{start}",
                start,
                end,
                body,
                max_characters=max_chunk_characters,
            ),
        )
        run.clear()

    for line_no in range(1, len(lines) + 1):
        if line_no in covered:
            flush()
            continue
        run.append(line_no)
    flush()
    return chunks


def _node_span(node: ast.AST) -> tuple[int, int]:
    """Line span of a node including its decorators."""
    start = getattr(node, "lineno", 1)
    decorators: Iterable[ast.expr] = getattr(node, "decorator_list", []) or []
    for decorator in decorators:
        start = min(start, decorator.lineno)
    end = getattr(node, "end_lineno", None) or start
    return start, end


# --------------------------------------------------------------------------- #
# Documents and fallback
# --------------------------------------------------------------------------- #


def parse_document(
    source: SourceFile, max_chunk_characters: int = DEFAULT_MAX_CHUNK_CHARACTERS
) -> list[CodeChunk]:
    """Chunk documentation and configuration files.

    Markdown is split on ATX headings so each section keeps its own heading as a
    symbol; other formats fall back to windowed chunking.
    """
    if source.language is not Language.MARKDOWN:
        return fallback_chunks(source, max_chunk_characters, ChunkType.DOCUMENT)

    lines = source.content.splitlines()
    sections: list[tuple[str, int]] = []
    for index, line in enumerate(lines, start=1):
        if line.startswith("#"):
            sections.append((line.lstrip("#").strip() or f"section:{index}", index))

    if not sections:
        return fallback_chunks(source, max_chunk_characters, ChunkType.DOCUMENT)

    chunks: list[CodeChunk] = []
    if sections[0][1] > 1:
        _append(
            chunks,
            make_chunk(
                source,
                ChunkType.DOCUMENT,
                f"{source.file_path}:preamble",
                1,
                sections[0][1] - 1,
                slice_lines(lines, 1, sections[0][1] - 1),
                max_characters=max_chunk_characters,
            ),
        )
    for position, (title, start) in enumerate(sections):
        end = (
            sections[position + 1][1] - 1
            if position + 1 < len(sections)
            else len(lines)
        )
        _append(
            chunks,
            make_chunk(
                source,
                ChunkType.DOCUMENT,
                title,
                start,
                end,
                slice_lines(lines, start, end),
                max_characters=max_chunk_characters,
            ),
        )
    return chunks


def fallback_chunks(
    source: SourceFile,
    max_chunk_characters: int = DEFAULT_MAX_CHUNK_CHARACTERS,
    chunk_type: ChunkType = ChunkType.MODULE,
    window: int = _FALLBACK_WINDOW_LINES,
    overlap: int = _FALLBACK_OVERLAP_LINES,
) -> list[CodeChunk]:
    """Overlapping line-window chunking, used only when parsing fails."""
    lines = source.content.splitlines()
    if not lines:
        return []
    step = max(window - overlap, 1)
    chunks: list[CodeChunk] = []
    for start in range(1, len(lines) + 1, step):
        end = min(start + window - 1, len(lines))
        _append(
            chunks,
            make_chunk(
                source,
                chunk_type,
                f"{source.file_path}:{start}",
                start,
                end,
                slice_lines(lines, start, end),
                max_characters=max_chunk_characters,
            ),
        )
        if end == len(lines):
            break
    return chunks


def _append(chunks: list[CodeChunk], chunk: CodeChunk | None) -> None:
    if chunk is not None:
        chunks.append(chunk)
