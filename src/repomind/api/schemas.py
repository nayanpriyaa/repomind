from __future__ import annotations

from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from ..models import (
    Answer,
    Citation,
    IndexReport,
    RepositoryStatus,
    RetrievedChunk,
    SearchMode,
)
from ..uploads import StoredRepository

MAX_QUESTION_LENGTH = 2_000
MAX_ID_LENGTH = 64

RepositoryId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=MAX_ID_LENGTH,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    ),
]


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str


class ReadinessResponse(BaseModel):
    ready: bool
    database: bool
    vector_store: bool
    llm_configured: bool


class IndexRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    repository_id: RepositoryId
    force: bool = False


class SkippedFileResponse(BaseModel):
    file_path: str
    reason: str


class IndexResponse(BaseModel):
    repository_id: str
    files_scanned: int
    files_indexed: int
    files_skipped: int
    files_unchanged: int
    files_deleted: int
    chunks_indexed: int
    chunks_deleted: int
    duration_seconds: float
    skipped: list[SkippedFileResponse] = Field(
        default_factory=list
    )

    @classmethod
    def from_report(
        cls,
        report: IndexReport,
        repository_id: str,
        skip_limit: int = 50,
    ) -> "IndexResponse":

        return cls(
            repository_id=repository_id,
            files_scanned=report.files_scanned,
            files_indexed=report.files_indexed,
            files_skipped=report.files_skipped,
            files_unchanged=report.files_unchanged,
            files_deleted=report.files_deleted,
            chunks_indexed=report.chunks_indexed,
            chunks_deleted=report.chunks_deleted,
            duration_seconds=round(
                report.duration_seconds,
                3,
            ),
            skipped=[
                SkippedFileResponse(
                    file_path=item.file_path,
                    reason=item.reason,
                )
                for item in report.skipped[
                    :skip_limit
                ]
            ],
        )


class StatusResponse(BaseModel):
    repository_id: str
    name: str
    indexed: bool
    file_count: int
    chunk_count: int
    stored_file_count: int = 0
    size_bytes: int = 0
    last_indexed_at: float | None = None
    languages: dict[str, int] = Field(
        default_factory=dict
    )

    @classmethod
    def build(
        cls,
        stored: StoredRepository,
        status: RepositoryStatus | None = None,
    ) -> "StatusResponse":

        return cls(
            repository_id=stored.repository_id,
            name=stored.name,
            indexed=bool(
                status and status.indexed
            ),
            file_count=(
                status.file_count
                if status
                else 0
            ),
            chunk_count=(
                status.chunk_count
                if status
                else 0
            ),
            stored_file_count=(
                stored.file_count
            ),
            size_bytes=stored.size_bytes,
            last_indexed_at=(
                status.last_indexed_at
                if status
                else None
            ),
            languages=(
                status.languages
                if status
                else {}
            ),
        )


class RepositoryListResponse(BaseModel):
    repositories: list[StatusResponse] = Field(
        default_factory=list
    )


class QueryRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    repository_id: RepositoryId
    question: str = Field(
        ...,
        min_length=3,
        max_length=MAX_QUESTION_LENGTH,
    )
    top_k: int = Field(
        5,
        ge=1,
        le=50,
    )
    mode: SearchMode = SearchMode.HYBRID


class SourceResponse(BaseModel):
    file_path: str
    start_line: int
    end_line: int
    symbol: str
    language: str
    chunk_type: str
    score: float

    @classmethod
    def from_citation(
        cls,
        citation: Citation,
    ) -> "SourceResponse":

        return cls(
            file_path=citation.file_path,
            start_line=citation.start_line,
            end_line=citation.end_line,
            symbol=citation.symbol,
            language=citation.language.value,
            chunk_type=citation.chunk_type.value,
            score=round(
                citation.score,
                6,
            ),
        )


class QueryResponse(BaseModel):
    question: str
    answer: str
    mode: SearchMode
    grounded: bool
    chunks_used: int
    context_characters: int
    sources: list[SourceResponse] = Field(
        default_factory=list
    )

    @classmethod
    def from_answer(
        cls,
        answer: Answer,
    ) -> "QueryResponse":

        return cls(
            question=answer.question,
            answer=answer.answer,
            mode=answer.mode,
            grounded=answer.grounded,
            chunks_used=answer.chunks_used,
            context_characters=answer.context_characters,
            sources=[
                SourceResponse.from_citation(
                    citation
                )
                for citation in answer.citations
            ],
        )


class SearchRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    repository_id: RepositoryId
    query: str = Field(
        ...,
        min_length=1,
        max_length=MAX_QUESTION_LENGTH,
    )
    top_k: int = Field(
        10,
        ge=1,
        le=50,
    )
    mode: SearchMode = SearchMode.HYBRID


class SearchHitResponse(BaseModel):
    chunk_id: str
    score: float
    file_path: str
    start_line: int
    end_line: int
    symbol: str
    language: str
    chunk_type: str
    match_type: str
    content: str

    @classmethod
    def from_chunk(
        cls,
        chunk: RetrievedChunk,
    ) -> "SearchHitResponse":

        return cls(
            chunk_id=chunk.chunk_id,
            score=round(
                chunk.score,
                6,
            ),
            file_path=chunk.file_path,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            symbol=chunk.symbol,
            language=chunk.language.value,
            chunk_type=chunk.chunk_type.value,
            match_type=chunk.match_type,
            content=chunk.content,
        )


class SearchResponse(BaseModel):
    query: str
    mode: SearchMode
    hits: list[SearchHitResponse] = Field(
        default_factory=list
    )


class UploadResponse(BaseModel):
    repository: StatusResponse
    message: str


class DeleteResponse(BaseModel):
    repository_id: str
    chunks_removed: int