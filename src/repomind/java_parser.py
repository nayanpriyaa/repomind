"""Java structural parsing via tree-sitter.

Java declarations all expose a ``name`` field, so symbol resolution is a direct
field read. Types are descended into so that methods and constructors become
their own chunks rather than being buried inside a large class chunk.
"""

from __future__ import annotations

import logging
from typing import Any

from .models import ChunkType, CodeChunk, SourceFile
from .parser import DEFAULT_MAX_CHUNK_CHARACTERS, fallback_chunks
from .treesitter_support import (
    LanguageRules,
    NodeRule,
    TreeSitterUnavailable,
    field_text,
    parse_with_rules,
)

logger = logging.getLogger(__name__)

JAVA_RULES = LanguageRules(
    grammar="java",
    rules={
        "class_declaration": NodeRule(ChunkType.CLASS, descend=True),
        "interface_declaration": NodeRule(ChunkType.INTERFACE, descend=True),
        "enum_declaration": NodeRule(ChunkType.ENUM, descend=True),
        "record_declaration": NodeRule(ChunkType.STRUCT, descend=True),
        "annotation_type_declaration": NodeRule(ChunkType.INTERFACE),
        "method_declaration": NodeRule(ChunkType.METHOD),
        "constructor_declaration": NodeRule(ChunkType.CONSTRUCTOR),
    },
)


def symbol_of(node: Any, data: bytes) -> str | None:
    """Read the ``name`` field of a Java declaration."""
    return field_text(node, data, "name")


def parse(
    source: SourceFile, max_chunk_characters: int = DEFAULT_MAX_CHUNK_CHARACTERS
) -> list[CodeChunk]:
    """Chunk a Java file, degrading to windows if the grammar is missing."""
    try:
        return parse_with_rules(source, JAVA_RULES, symbol_of, max_chunk_characters)
    except TreeSitterUnavailable:
        logger.info("tree-sitter java grammar unavailable; windowing %s", source.file_path)
        return fallback_chunks(source, max_chunk_characters)
