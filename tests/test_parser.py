"""Structural chunking: the shape of what ends up in the index."""

from __future__ import annotations

from conftest import MARKDOWN_SAMPLE, PYTHON_SAMPLE, make_source

from repomind.models import ChunkType, Language
from repomind.parser import fallback_chunks, parse_file, parse_python


def by_symbol(chunks):
    return {chunk.symbol: chunk for chunk in chunks}


def test_python_functions_and_methods_are_separate_chunks() -> None:
    chunks = by_symbol(parse_python(make_source(PYTHON_SAMPLE)))
    assert chunks["authenticate"].chunk_type is ChunkType.FUNCTION
    assert chunks["TokenService.issue"].chunk_type is ChunkType.METHOD
    assert chunks["TokenService.__init__"].chunk_type is ChunkType.CONSTRUCTOR
    assert chunks["TokenService.validate"].chunk_type is ChunkType.ASYNC_FUNCTION or (
        chunks["TokenService.validate"].chunk_type is ChunkType.METHOD
    )


def test_class_chunk_excludes_its_method_bodies() -> None:
    chunks = by_symbol(parse_python(make_source(PYTHON_SAMPLE)))
    class_chunk = chunks["TokenService"]
    assert class_chunk.chunk_type is ChunkType.CLASS
    assert "algorithm" in class_chunk.content
    assert "hashlib.sha256" not in class_chunk.content


def test_methods_record_their_parent_class() -> None:
    chunks = by_symbol(parse_python(make_source(PYTHON_SAMPLE)))
    assert chunks["TokenService.issue"].parent_symbol == "TokenService"


def test_line_ranges_point_at_the_real_source() -> None:
    source = make_source(PYTHON_SAMPLE)
    chunk = by_symbol(parse_python(source))["authenticate"]
    lines = source.content.splitlines()
    assert lines[chunk.start_line - 1].startswith("def authenticate")
    assert chunk.end_line >= chunk.start_line


def test_module_level_code_is_preserved() -> None:
    chunks = parse_python(make_source(PYTHON_SAMPLE))
    module_chunks = [c for c in chunks if c.chunk_type is ChunkType.MODULE]
    assert module_chunks, "module-level imports and constants must be indexed"
    assert any("import hashlib" in chunk.content for chunk in module_chunks)


def test_decorated_functions_include_their_decorators() -> None:
    source = make_source(
        "import functools\n\n\n@functools.cache\ndef memoized(value):\n    return value * 2\n"
    )
    chunk = by_symbol(parse_python(source))["memoized"]
    assert "@functools.cache" in chunk.content


def test_chunk_ids_are_deterministic_across_runs() -> None:
    first = parse_python(make_source(PYTHON_SAMPLE))
    second = parse_python(make_source(PYTHON_SAMPLE))
    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]
    assert len({c.chunk_id for c in first}) == len(first)


def test_syntax_errors_degrade_to_windows_instead_of_raising() -> None:
    chunks = parse_file(make_source("def broken(:\n    ???\n    more garbage here\n"))
    assert chunks, "unparseable files must still be searchable"
    assert all(chunk.chunk_type is ChunkType.MODULE for chunk in chunks)


def test_markdown_is_split_on_headings() -> None:
    chunks = parse_file(
        make_source(MARKDOWN_SAMPLE, file_path="README.md", language=Language.MARKDOWN)
    )
    symbols = {chunk.symbol for chunk in chunks}
    assert {"Installation", "Usage"} <= symbols
    assert all(chunk.chunk_type is ChunkType.DOCUMENT for chunk in chunks)


def test_fallback_windows_overlap_and_cover_the_file() -> None:
    source = make_source("\n".join(f"line_{i} = {i}" for i in range(1, 121)))
    chunks = fallback_chunks(source, window=50, overlap=10)
    assert len(chunks) >= 2
    assert chunks[0].start_line == 1
    assert chunks[-1].end_line == 120
    assert chunks[1].start_line < chunks[0].end_line  # overlapping


def test_oversized_chunks_are_truncated_not_dropped() -> None:
    body = "\n".join(f"    step_{i}()" for i in range(2000))
    source = make_source(f"def huge():\n{body}\n")
    chunk = by_symbol(parse_python(source))["huge"]
    assert len(chunk.content) < 7_000
    assert chunk.content.endswith("[truncated]")


def test_empty_file_produces_no_chunks() -> None:
    assert parse_file(make_source("")) == []
