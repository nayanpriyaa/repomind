"""FastAPI application.

The container lives on ``app.state`` and is created once during lifespan
startup, so the embedding model, Qdrant client and other services are shared
between requests.

Repositories are addressed externally by a safe repository ID. Filesystem
paths never appear in API requests or responses. Uploaded ZIP archives are
managed by RepositoryStore and extracted into the configured repository root.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from .. import __version__
from ..config import (
    RepositoryAccessError,
    Settings,
    configure_logging,
)
from ..container import (
    ServiceContainer,
    build_container,
)
from ..llm import LLMError
from ..retrieval import RetrievalRequest
from ..uploads import (
    RepositoryExistsError,
    RepositoryNotFoundError,
    RepositoryStore,
    RepositoryUploadError,
)
from .schemas import (
    DeleteResponse,
    HealthResponse,
    IndexRequest,
    IndexResponse,
    QueryRequest,
    QueryResponse,
    ReadinessResponse,
    RepositoryListResponse,
    SearchHitResponse,
    SearchRequest,
    SearchResponse,
    StatusResponse,
    UploadResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_container(
    request: Request,
) -> ServiceContainer:
    """Expose the process-wide service container."""
    return request.app.state.container


# ---------------------------------------------------------------------------
# Repository helpers
# ---------------------------------------------------------------------------


def _path_of(
    container: ServiceContainer,
    repository_id: str,
):
    """Resolve a stored repository ID to its internal filesystem path.

    The ID comes from the validated API schema, then RepositoryStore resolves
    it to a stored directory. We run the resulting path through the configured
    repository-root allowlist again as defence in depth.

    The path is an internal implementation detail and is never returned to the
    client.
    """
    try:
        stored = container.repository_store.describe(
            repository_id
        )

        # Re-check through the configured repository-root allowlist.
        resolved = (
            container.settings.resolve_repository_path(
                stored.path
            )
        )

        return resolved

    except (
        RepositoryNotFoundError,
        RepositoryAccessError,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="repository not found",
        ) from None


def _status_for(
    container: ServiceContainer,
    repository_id: str,
) -> StatusResponse:
    """Build the public status representation for a stored repository."""
    stored = container.repository_store.describe(
        repository_id
    )

    repository_path = (
        container.settings.resolve_repository_path(
            stored.path
        )
    )

    index_status = container.index_state.status(
        str(repository_path)
    )

    return StatusResponse.build(
        stored,
        index_status,
    )


# ---------------------------------------------------------------------------
# System endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["system"],
)
async def health() -> HealthResponse:
    """Liveness probe.

    This deliberately does not touch SQLite, Qdrant or Ollama.
    """
    return HealthResponse(
        status="ok",
        version=__version__,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    tags=["system"],
)
async def ready(
    container: ServiceContainer = Depends(
        get_container
    ),
) -> ReadinessResponse:
    """Report readiness of RepoMind dependencies."""
    report = await run_in_threadpool(
        container.health
    )

    return ReadinessResponse(
        ready=report.ready,
        database=report.database,
        vector_store=report.vector_store,
        llm_configured=report.llm_configured,
    )


# ---------------------------------------------------------------------------
# Repository listing / lookup
# ---------------------------------------------------------------------------


@router.get(
    "/repositories",
    response_model=RepositoryListResponse,
    tags=["repositories"],
)
async def list_repositories(
    container: ServiceContainer = Depends(
        get_container
    ),
) -> RepositoryListResponse:
    """Return every repository currently stored on disk.

    This intentionally starts from RepositoryStore rather than SQLite so a
    freshly uploaded repository appears immediately, before it has been
    indexed.
    """

    stored_repositories = await run_in_threadpool(
        container.repository_store.list
    )

    results: list[StatusResponse] = []

    for stored in stored_repositories:
        try:
            repository_path = (
                container.settings.resolve_repository_path(
                    stored.path
                )
            )

            index_status = await run_in_threadpool(
                container.index_state.status,
                str(repository_path),
            )

            results.append(
                StatusResponse.build(
                    stored,
                    index_status,
                )
            )

        except RepositoryAccessError:
            # A repository directory should never escape the configured root.
            # If one somehow does, do not expose it through the API.
            logger.warning(
                "ignoring repository outside configured root: %s",
                stored.repository_id,
            )

    results.sort(
        key=lambda item: item.repository_id
    )

    return RepositoryListResponse(
        repositories=results
    )


@router.get(
    "/repositories/{repository_id}",
    response_model=StatusResponse,
    tags=["repositories"],
)
async def get_repository(
    repository_id: str,
    container: ServiceContainer = Depends(
        get_container
    ),
) -> StatusResponse:
    """Return storage and indexing information for one repository."""
    return await run_in_threadpool(
        _status_for,
        container,
        repository_id,
    )


# ---------------------------------------------------------------------------
# Repository upload
# ---------------------------------------------------------------------------


@router.post(
    "/repositories/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["repositories"],
)
async def upload_repository(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    overwrite: bool = Query(
        default=False
    ),
    container: ServiceContainer = Depends(
        get_container
    ),
) -> UploadResponse:
    """Upload a ZIP archive and store it as a managed repository.

    The archive is streamed into RepositoryStore, which enforces archive-size,
    entry-count, expansion-size and compression-ratio limits before extracting
    it. Extraction happens in staging and is moved into place only after the
    complete archive has passed validation.
    """

    filename = (
        file.filename
        or "repository.zip"
    )

    requested_name = (
        name.strip()
        if name is not None
        else None
    )

    if requested_name == "":
        requested_name = None

    try:
        stored = await run_in_threadpool(
            container.repository_store.create_from_zip,
            file.file,
            requested_name or filename,
            requested_name,
            overwrite,
        )

    except RepositoryExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from None

    except RepositoryUploadError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from None

    except Exception as exc:
        logger.exception(
            "repository upload failed for %s",
            filename,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "repository upload failed: "
                f"{exc.__class__.__name__}"
            ),
        ) from None

    finally:
        await file.close()

    # A newly uploaded repository has no index state yet. StatusResponse.build
    # therefore correctly reports indexed=False and zero indexed files/chunks.
    response = StatusResponse.build(
        stored,
        None,
    )

    return UploadResponse(
        repository=response,
        message=(
            "repository uploaded successfully"
        ),
    )


# ---------------------------------------------------------------------------
# Repository deletion
# ---------------------------------------------------------------------------


@router.delete(
    "/repositories/{repository_id}",
    response_model=DeleteResponse,
    tags=["repositories"],
)
async def delete_repository(
    repository_id: str,
    container: ServiceContainer = Depends(
        get_container
    ),
) -> DeleteResponse:
    """Delete a repository from disk and every index."""

    repository_path = _path_of(
        container,
        repository_id,
    )

    try:
        chunks_removed = await run_in_threadpool(
            container.ingestion.delete_repository,
            str(repository_path),
        )

        # The ingestion layer removes SQLite state and vector/keyword entries.
        # RepositoryStore then removes the actual uploaded source tree.
        await run_in_threadpool(
            container.repository_store.delete,
            repository_id,
        )

    except RepositoryNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="repository not found",
        ) from None

    except Exception as exc:
        logger.exception(
            "failed to delete repository %s",
            repository_id,
        )

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "repository deletion failed: "
                f"{exc.__class__.__name__}"
            ),
        ) from None

    return DeleteResponse(
        repository_id=repository_id,
        chunks_removed=chunks_removed,
    )


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------


@router.post(
    "/repositories/index",
    response_model=IndexResponse,
    tags=["repositories"],
)
async def index_repository(
    payload: IndexRequest,
    container: ServiceContainer = Depends(
        get_container
    ),
) -> IndexResponse:
    """Index or incrementally re-index a stored repository."""

    repository_path = _path_of(
        container,
        payload.repository_id,
    )

    try:
        report = await run_in_threadpool(
            container.ingestion.index_repository,
            str(repository_path),
            payload.force,
        )

    except Exception as exc:
        logger.exception(
            "indexing failed for %s",
            payload.repository_id,
        )

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "indexing failed: "
                f"{exc.__class__.__name__}"
            ),
        ) from None

    return IndexResponse.from_report(
        report,
        payload.repository_id,
    )


# ---------------------------------------------------------------------------
# Repository status
# ---------------------------------------------------------------------------


@router.get(
    "/repositories/status",
    response_model=StatusResponse,
    tags=["repositories"],
)
async def repository_status_legacy(
    repository_id: str = Query(...),
    container: ServiceContainer = Depends(
        get_container
    ),
) -> StatusResponse:
    """Compatibility status endpoint.

    New clients should use:
        GET /repositories/{repository_id}
    """
    return await run_in_threadpool(
        _status_for,
        container,
        repository_id,
    )


# ---------------------------------------------------------------------------
# Q&A
# ---------------------------------------------------------------------------


@router.post(
    "/repositories/query",
    response_model=QueryResponse,
    tags=["repositories"],
)
async def query_repository(
    payload: QueryRequest,
    container: ServiceContainer = Depends(
        get_container
    ),
) -> QueryResponse:
    """Answer a question about an indexed repository."""

    repository_path = _path_of(
        container,
        payload.repository_id,
    )

    try:
        answer = await run_in_threadpool(
            container.rag.answer,
            payload.question,
            str(repository_path),
            payload.top_k,
            payload.mode,
        )

    except LLMError as exc:
        logger.error(
            "LLM failure for %s: %s",
            payload.repository_id,
            exc,
        )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "the language model provider "
                "is unavailable"
            ),
        ) from None

    except Exception as exc:
        logger.exception(
            "query failed for %s",
            payload.repository_id,
        )

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "query failed: "
                f"{exc.__class__.__name__}"
            ),
        ) from None

    return QueryResponse.from_answer(
        answer
    )


# ---------------------------------------------------------------------------
# Raw retrieval
# ---------------------------------------------------------------------------


@router.post(
    "/repositories/search",
    response_model=SearchResponse,
    tags=["retrieval"],
)
async def search_repository(
    payload: SearchRequest,
    container: ServiceContainer = Depends(
        get_container
    ),
) -> SearchResponse:
    """Perform raw retrieval without LLM generation."""

    repository_path = _path_of(
        container,
        payload.repository_id,
    )

    retrieval_request = RetrievalRequest(
        query=payload.query,
        mode=payload.mode,
        top_k=payload.top_k,
        repository_path=str(
            repository_path
        ),
    )

    try:
        hits = await run_in_threadpool(
            container.retrieval.search,
            retrieval_request,
        )

    except Exception as exc:
        logger.exception(
            "search failed for %s",
            payload.repository_id,
        )

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "search failed: "
                f"{exc.__class__.__name__}"
            ),
        ) from None

    return SearchResponse(
        query=payload.query,
        mode=payload.mode,
        hits=[
            SearchHitResponse.from_chunk(
                hit
            )
            for hit in hits
        ],
    )


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app(
    settings: Settings | None = None,
    container: ServiceContainer | None = None,
) -> FastAPI:
    """Create the RepoMind FastAPI application.

    Tests can inject a pre-built ServiceContainer with in-memory dependencies.
    Production uses the normal ServiceContainer created from environment
    configuration.
    """

    resolved_settings = (
        settings
        or (
            container.settings
            if container is not None
            else Settings.from_env()
        )
    )

    configure_logging(
        resolved_settings.log_level
    )

    @asynccontextmanager
    async def lifespan(
        app: FastAPI,
    ) -> AsyncIterator[None]:
        app.state.container = (
            container
            or build_container(
                resolved_settings
            )
        )

        await run_in_threadpool(
            app.state.container.startup
        )

        logger.info(
            "RepoMind %s ready",
            __version__,
        )

        yield

    app = FastAPI(
        title="RepoMind",
        version=__version__,
        description=(
            "LLM-powered codebase analysis "
            "and semantic search."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=(
            resolved_settings
            .cors_allow_origins
        ),
        allow_credentials=False,
        allow_methods=[
            "GET",
            "POST",
            "DELETE",
        ],
        allow_headers=[
            "Content-Type",
        ],
    )

    app.include_router(router)

    return app


app = create_app()