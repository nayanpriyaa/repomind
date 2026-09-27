"""JavaScript, TypeScript and TSX structural parsing via tree-sitter.

Modern JS/TS code expresses most units as ``const x = () => {}`` rather than as
function declarations, so ``variable_declarator`` nodes whose value is a function
or arrow function are captured too. Export wrappers need no special handling:
unmatched nodes are traversed transparently by the shared walker.
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
    field_text,
    parse_with_rules,
    text_of,
)

logger = logging.getLogger(__name__)

_FUNCTION_VALUE_TYPES = {
    "arrow_function",
    "function",
    "function_expression",
    "generator_function",
}

_BASE_RULES: dict[str, NodeRule] = {
    "function_declaration": NodeRule(ChunkType.FUNCTION),
    "generator_function_declaration": NodeRule(ChunkType.FUNCTION),
    "class_declaration": NodeRule(ChunkType.CLASS, descend=True),
    "class": NodeRule(ChunkType.CLASS, descend=True),
    "method_definition": NodeRule(ChunkType.METHOD),
    "variable_declarator": NodeRule(ChunkType.FUNCTION),
}

_TS_RULES: dict[str, NodeRule] = {
    **_BASE_RULES,
    "interface_declaration": NodeRule(ChunkType.INTERFACE),
    "type_alias_declaration": NodeRule(ChunkType.INTERFACE),
    "enum_declaration": NodeRule(ChunkType.ENUM),
    "abstract_class_declaration": NodeRule(ChunkType.CLASS, descend=True),
}

_GRAMMARS = {
    Language.JAVASCRIPT: LanguageRules(grammar="javascript", rules=_BASE_RULES),
    Language.TYPESCRIPT: LanguageRules(grammar="typescript", rules=_TS_RULES),
    Language.TSX: LanguageRules(grammar="tsx", rules=_TS_RULES),
}


def symbol_of(node: Any, data: bytes) -> str | None:
    """Resolve a symbol name, ignoring non-function variable declarators."""
    if node.type == "variable_declarator":
        value = node.child_by_field_name("value")
        if value is None or value.type not in _FUNCTION_VALUE_TYPES:
            return None
        return field_text(node, data, "name")
    name = field_text(node, data, "name")
    if name:
        return name
    key = node.child_by_field_name("key") or node.child_by_field_name("property")
    return text_of(key, data) if key is not None else None


def parse(
    source: SourceFile, max_chunk_characters: int = DEFAULT_MAX_CHUNK_CHARACTERS
) -> list[CodeChunk]:
    """Chunk a JS/TS/TSX file, degrading to windows if the grammar is missing."""
    rules = _GRAMMARS.get(source.language, _GRAMMARS[Language.JAVASCRIPT])
    try:
        return parse_with_rules(source, rules, symbol_of, max_chunk_characters)
    except TreeSitterUnavailable:
        logger.info(
            "tree-sitter grammar %s unavailable; windowing %s",
            rules.grammar,
            source.file_path,
        )
        return fallback_chunks(source, max_chunk_characters)
