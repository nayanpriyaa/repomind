"""Grounded context construction.

Turns ranked chunks into the evidence block handed to the LLM. Three jobs:

1. **Deduplicate.** Hybrid retrieval and overlapping fallback windows routinely
   surface the same source twice; paying for it twice wastes the budget and
   biases the model toward repeated text.
2. **Budget.** The context is capped in characters, in rank order, so the best
   evidence survives truncation.
3. **Neutralise.** Repository content is untrusted. Delimiters that would let a
   file close the evidence block and start issuing instructions are defanged
   here, before the text reaches the prompt template.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

from .file_hash import hash_text
from .models import Citation, RetrievedChunk

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONTEXT_CHARACTERS = 24_000
_MIN_USEFUL_CHARACTERS = 200
_TRUNCATION_SUFFIX = "\n... [truncated]\n</evidence>"

_DELIMITER_REPLACEMENTS = {
    "</evidence>": "<\u200b/evidence>",
    "<evidence>": "<\u200bevidence>",
    "</repository_evidence>": "<\u200b/repository_evidence>",
    "<repository_evidence>": "<\u200brepository_evidence>",
}


@dataclass(frozen=True, slots=True)
class ContextBlock:
    """One rendered evidence block plus the citation it corresponds to."""

    text: str
    citation: Citation


@dataclass(frozen=True, slots=True)
class BuiltContext:
    """The complete evidence payload for one question."""

    text: str
    citations: list[Citation]
    chunks_used: int
    characters: int

    @property
    def is_empty(self) -> bool:
        return self.chunks_used == 0


def build_context(
    chunks: Sequence[RetrievedChunk],
    max_characters: int = DEFAULT_MAX_CONTEXT_CHARACTERS,
) -> BuiltContext:
    """Render ranked chunks into a bounded, deduplicated evidence block."""
    blocks: list[ContextBlock] = []
    seen_content: set[str] = set()
    seen_location: set[tuple[str, int, int]] = set()
    used = 0

    for index, chunk in enumerate(chunks, start=1):
        location = (chunk.file_path, chunk.start_line, chunk.end_line)
        fingerprint = hash_text(chunk.content.strip())
        if location in seen_location or fingerprint in seen_content:
            continue

        rendered = _render_block(index, chunk)
        remaining = max_characters - used
        if len(rendered) > remaining:
            if remaining < _MIN_USEFUL_CHARACTERS:
                break
            # Reserve room for the closing marker so the budget is never exceeded.
            budget = remaining - len(_TRUNCATION_SUFFIX)
            rendered = rendered[:budget].rstrip() + _TRUNCATION_SUFFIX

        seen_location.add(location)
        seen_content.add(fingerprint)
        used += len(rendered)
        blocks.append(ContextBlock(text=rendered, citation=_citation(chunk)))

    return BuiltContext(
        text="\n".join(block.text for block in blocks),
        citations=[block.citation for block in blocks],
        chunks_used=len(blocks),
        characters=used,
    )


def _render_block(index: int, chunk: RetrievedChunk) -> str:
    """Render one chunk with attributes the model can quote in a citation."""
    body = sanitize(chunk.content)
    return (
        f'<evidence id="{index}" file="{chunk.file_path}" '
        f'lines="{chunk.start_line}-{chunk.end_line}" '
        f'language="{chunk.language.value}" '
        f'kind="{chunk.chunk_type.value}" symbol="{_attr(chunk.symbol)}">\n'
        f"{body}\n"
        "</evidence>"
    )


def sanitize(text: str) -> str:
    """Strip control characters and defuse evidence-block delimiters."""
    cleaned = "".join(
        character
        for character in text
        if character in "\n\t" or character >= " " or character == "\r"
    )
    for needle, replacement in _DELIMITER_REPLACEMENTS.items():
        cleaned = cleaned.replace(needle, replacement)
        cleaned = cleaned.replace(needle.upper(), replacement)
    return cleaned


def _attr(value: str) -> str:
    """Escape a value for safe use inside a double-quoted XML-ish attribute."""
    return value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def _citation(chunk: RetrievedChunk) -> Citation:
    return Citation(
        file_path=chunk.file_path,
        start_line=chunk.start_line,
        end_line=chunk.end_line,
        symbol=chunk.symbol,
        language=chunk.language,
        chunk_type=chunk.chunk_type,
        score=chunk.score,
    )
