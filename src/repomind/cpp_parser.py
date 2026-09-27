"""C and C++ structural parsing via tree-sitter.

C declarators nest (``static int *foo(int)`` is a pointer declarator wrapping a
function declarator wrapping an identifier), so the symbol name is resolved by
descending to the first identifier-like node rather than by reading a field.
"""

from __future__ import annotations

import logging
from typing import Any

from .models import ChunkType, CodeChunk, Language, SourceFile
from .parser import DEFAULT_MAX_CHUNK_CHARACTERS, fallback_chunks
from .treesitter_support import (
    LanguageRules,
    NodeRule,
    TreeSitterUnavailable,
    first_descendant_text,
    parse_with_rules,
    text_of,
)

logger = logging.getLogger(__name__)

_IDENTIFIER_TYPES = (
    "identifier",
    "field_identifier",
    "type_identifier",
    "qualified_identifier",
    "operator_name",
    "destructor_name",
)

_RULES: dict[str, NodeRule] = {
    "function_definition": NodeRule(ChunkType.FUNCTION),
    "class_specifier": NodeRule(
        ChunkType.CLASS, descend=True, nested_chunk_type=ChunkType.METHOD
    ),
    "struct_specifier": NodeRule(
        ChunkType.STRUCT, descend=True, nested_chunk_type=ChunkType.METHOD
    ),
    "union_specifier": NodeRule(ChunkType.STRUCT),
    "enum_specifier": NodeRule(ChunkType.ENUM),
}

C_RULES = LanguageRules(grammar="c", rules=_RULES)
CPP_RULES = LanguageRules(grammar="cpp", rules=_RULES)


def symbol_of(node: Any, data: bytes) -> str | None:
    """Best-effort symbol name for a C/C++ declaration node."""
    declarator = node.child_by_field_name("declarator")
    if declarator is not None:
        name = first_descendant_text(declarator, data, _IDENTIFIER_TYPES)
        if name:
            return name
        return text_of(declarator, data).strip() or None
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return text_of(name_node, data)
    return first_descendant_text(node, data, _IDENTIFIER_TYPES)


def parse(
    source: SourceFile, max_chunk_characters: int = DEFAULT_MAX_CHUNK_CHARACTERS
) -> list[CodeChunk]:
    """Chunk a C or C++ file, degrading to windows if the grammar is missing."""
    rules = C_RULES if source.language is Language.C else CPP_RULES
    try:
        return parse_with_rules(source, rules, symbol_of, max_chunk_characters)
    except TreeSitterUnavailable:
        logger.info(
            "tree-sitter grammar %s unavailable; windowing %s",
            rules.grammar,
            source.file_path,
        )
        return fallback_chunks(source, max_chunk_characters)
