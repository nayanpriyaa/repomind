"""Shared tree-sitter infrastructure for the non-Python parsers.

Grammar loading is deliberately tolerant: several distributions of the Python
bindings exist (``tree-sitter-language-pack``, the older ``tree-sitter-languages``
and per-language wheels such as ``tree-sitter-java``). All three are tried in
order and the result is cached, so a missing grammar degrades one language to
windowed chunking instead of breaking the whole indexer.

The traversal here is generic. Each language module supplies a small ruleset -
which node types produce chunks, which of them should still be descended into,
and how to read a symbol name - and this module does the walking.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Iterator, Sequence

from .models import ChunkType, CodeChunk, SourceFile
from .parser import make_chunk, module_chunks

logger = logging.getLogger(__name__)


class TreeSitterUnavailable(RuntimeError):
    """Raised when no usable grammar can be loaded for a language."""


@dataclass(frozen=True, slots=True)
class NodeRule:
    """How to turn one tree-sitter node type into a chunk."""

    chunk_type: ChunkType
    descend: bool = False
    """Emit a chunk *and* keep walking children (used for classes with methods)."""

    nested_chunk_type: ChunkType | None = None
    """Chunk type applied to captured descendants, e.g. methods inside a class."""


@dataclass(frozen=True, slots=True)
class LanguageRules:
    """Complete chunking ruleset for one tree-sitter grammar.

    Node types that are absent from ``rules`` produce no chunk but are still
    traversed, so wrapper nodes (``export_statement``, ``template_declaration``,
    ``namespace_definition``) need no special casing.
    """

    grammar: str
    rules: dict[str, NodeRule]


@lru_cache(maxsize=None)
def get_parser(grammar: str) -> Any:
    """Return a cached tree-sitter ``Parser`` configured for ``grammar``."""
    try:
        import tree_sitter  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise TreeSitterUnavailable("tree-sitter is not installed") from exc

    language = _load_language(grammar)
    from tree_sitter import Parser

    try:
        return Parser(language)
    except TypeError:  # pragma: no cover - tree-sitter < 0.22 API
        parser = Parser()
        parser.set_language(language)
        return parser


def _load_language(grammar: str) -> Any:
    """Locate a grammar through whichever binding distribution is installed."""
    try:
        from tree_sitter_language_pack import get_language

        return get_language(grammar)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001 - fall through to the next provider
        pass

    try:
        from tree_sitter_languages import get_language as legacy_get_language

        return legacy_get_language(grammar)
    except Exception:  # noqa: BLE001
        pass

    module_name = f"tree_sitter_{grammar.replace('-', '_')}"
    try:
        import importlib

        from tree_sitter import Language

        module = importlib.import_module(module_name)
        return Language(module.language())
    except Exception as exc:  # noqa: BLE001
        raise TreeSitterUnavailable(
            f"no tree-sitter grammar available for {grammar!r}"
        ) from exc


def parse_with_rules(
    source: SourceFile,
    rules: LanguageRules,
    symbol_of: Callable[[Any, bytes], str | None],
    max_chunk_characters: int,
) -> list[CodeChunk]:
    """Parse ``source`` with tree-sitter and apply ``rules``.

    Raises :class:`TreeSitterUnavailable` when the grammar is missing; callers
    are expected to fall back to windowed chunking.
    """
    parser = get_parser(rules.grammar)
    data = source.content.encode("utf-8")
    tree = parser.parse(data)

    chunks: list[CodeChunk] = []
    covered: list[tuple[int, int]] = []

    for node, rule, parent in _walk(tree.root_node, rules):
        chunk_type = rule.chunk_type
        if parent is not None and parent[1].nested_chunk_type is not None:
            chunk_type = parent[1].nested_chunk_type
        symbol = symbol_of(node, data)
        if not symbol:
            # A rule matched structurally but the node carries no real symbol
            # (e.g. `const x = 1` matching `variable_declarator`). Leave it to
            # the residual pass so the source is still indexed, just not as a
            # named declaration.
            continue
        parent_symbol = symbol_of(parent[0], data) if parent is not None else None
        if parent_symbol:
            symbol = f"{parent_symbol}.{symbol}"

        start_line = node.start_point[0] + 1
        end_line = node.end_point[0] + 1
        chunk = make_chunk(
            source,
            chunk_type,
            symbol,
            start_line,
            end_line,
            data[node.start_byte : node.end_byte].decode("utf-8", errors="replace"),
            parent_symbol=parent_symbol,
            max_characters=max_chunk_characters,
        )
        if chunk is not None:
            chunks.append(chunk)
            covered.append((start_line, end_line))

    chunks.extend(
        _residual_chunks(source, covered, max_chunk_characters)
    )
    return chunks


def _walk(
    root: Any, rules: LanguageRules
) -> Iterator[tuple[Any, NodeRule, tuple[Any, NodeRule] | None]]:
    """Depth-first walk yielding ``(node, rule, parent)`` for matching nodes."""
    stack: list[tuple[Any, tuple[Any, NodeRule] | None]] = [(root, None)]
    while stack:
        node, parent = stack.pop()
        rule = rules.rules.get(node.type)

        if rule is not None:
            yield node, rule, parent
            if not rule.descend:
                continue
            parent = (node, rule)

        for child in reversed(node.children):
            stack.append((child, parent))


def _residual_chunks(
    source: SourceFile,
    covered: Sequence[tuple[int, int]],
    max_chunk_characters: int,
) -> list[CodeChunk]:
    """Capture top-level code (includes, globals, imports) outside declarations."""
    lines = source.content.splitlines()
    if not lines:
        return []
    inside: set[int] = set()
    for start, end in covered:
        inside.update(range(start, end + 1))
    return module_chunks(source, lines, inside, max_chunk_characters)


def text_of(node: Any, data: bytes) -> str:
    """UTF-8 text covered by ``node``."""
    return data[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def field_text(node: Any, data: bytes, field_name: str) -> str | None:
    """Text of a named field on ``node``, if present."""
    child = node.child_by_field_name(field_name)
    return text_of(child, data) if child is not None else None


def first_descendant_text(node: Any, data: bytes, types: Sequence[str]) -> str | None:
    """Breadth-first search for the first descendant of one of ``types``."""
    queue = list(node.children)
    while queue:
        current = queue.pop(0)
        if current.type in types:
            return text_of(current, data)
        queue.extend(current.children)
    return None
