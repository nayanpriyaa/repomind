"""Domain models shared by every layer of RepoMind.

Plain dataclasses and enums with no third-party dependencies, so the storage,
retrieval, RAG and API layers speak one vocabulary without leaking
vendor-specific types (Qdrant records, sqlite rows) across module boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Language(str, Enum):
    """Languages RepoMind can classify."""

    PYTHON = "python"
    C = "c"
    CPP = "cpp"
    JAVA = "java"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    TSX = "tsx"
    MARKDOWN = "markdown"
    JSON = "json"
    YAML = "yaml"
    TOML = "toml"
    UNKNOWN = "unknown"

    @property
    def is_code(self) -> bool:
        return self in _CODE_LANGUAGES


_CODE_LANGUAGES = frozenset(
    {
        Language.PYTHON,
        Language.C,
        Language.CPP,
        Language.JAVA,
        Language.JAVASCRIPT,
        Language.TYPESCRIPT,
        Language.TSX,
    }
)


class ChunkType(str, Enum):
    """Structural role of a chunk inside its source file."""

    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    ASYNC_FUNCTION = "async_function"
    METHOD = "method"
    CONSTRUCTOR = "constructor"
    STRUCT = "struct"
    INTERFACE = "interface"
    ENUM = "enum"
    DOCUMENT = "document"


class SearchMode(str, Enum):
    """Retrieval strategy requested by the caller."""

    SEMANTIC = "semantic"
    KEYWORD = "keyword"
    HYBRID = "hybrid"


@dataclass(frozen=True, slots=True)
class SourceFile:
    """A readable, in-scope text file discovered by the scanner."""

    repository_path: str
    file_path: str
    """Repository-relative POSIX path. Never absolute, never contains '..'."""

    absolute_path: str
    language: Language
    size_bytes: int
    sha256: str
    content: str

    @property
    def line_count(self) -> int:
        return self.content.count("\n") + 1


@dataclass(frozen=True, slots=True)
class SkippedFile:
    """A file the scanner deliberately refused to index, with the reason."""

    file_path: str
    reason: str


@dataclass(frozen=True, slots=True)
class CodeChunk:
    """A structurally meaningful unit of code or documentation."""

    chunk_id: str
    repository_path: str
    file_path: str
    language: Language
    chunk_type: ChunkType
    symbol: str
    start_line: int
    end_line: int
    content: str
    parent_symbol: str | None = None

    @property
    def location(self) -> str:
        return f"{self.file_path}:{self.start_line}-{self.end_line}"

    def to_payload(self) -> dict[str, Any]:
        """Flat, JSON-safe representation stored as the vector payload."""
        return {
            "repository_path": self.repository_path,
            "file_path": self.file_path,
            "language": self.language.value,
            "chunk_type": self.chunk_type.value,
            "symbol": self.symbol,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "content": self.content,
            "parent_symbol": self.parent_symbol,
        }


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """A chunk returned by retrieval, normalised across all backends."""

    chunk_id: str
    score: float
    repository_path: str
    file_path: str
    language: Language
    chunk_type: ChunkType
    symbol: str
    start_line: int
    end_line: int
    content: str
    match_type: str = "semantic"
    semantic_rank: int | None = None
    keyword_rank: int | None = None

    @property
    def location(self) -> str:
        return f"{self.file_path}:{self.start_line}-{self.end_line}"


@dataclass(frozen=True, slots=True)
class FileDiff:
    """Comparison of the working tree against persisted index state."""

    new: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    @property
    def requires_work(self) -> bool:
        return bool(self.new or self.modified or self.deleted)


@dataclass(frozen=True, slots=True)
class IndexReport:
    """Summary of a single indexing run."""

    repository_path: str
    files_scanned: int
    files_indexed: int
    files_skipped: int
    files_unchanged: int
    files_deleted: int
    chunks_indexed: int
    chunks_deleted: int
    duration_seconds: float
    skipped: list[SkippedFile] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RepositoryStatus:
    """Persisted view of what is currently indexed for a repository."""

    repository_path: str
    indexed: bool
    file_count: int
    chunk_count: int
    last_indexed_at: float | None
    languages: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Citation:
    """A file/line reference attached to an answer."""

    file_path: str
    start_line: int
    end_line: int
    symbol: str
    language: Language
    chunk_type: ChunkType
    score: float


@dataclass(frozen=True, slots=True)
class Answer:
    """Final RAG output."""

    question: str
    answer: str
    mode: SearchMode
    citations: list[Citation]
    chunks_used: int
    context_characters: int
    grounded: bool
