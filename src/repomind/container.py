from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import cached_property

from .config import Settings
from .embeddings import Embedder, build_embedder
from .index_state import IndexState
from .ingestion import IngestionService
from .keyword_search import KeywordIndex
from .llm import LLMClient, build_llm
from .rag import RagService
from .retrieval import RetrievalService
from .scanner import RepositoryScanner, ScannerConfig
from .uploads import RepositoryStore
from .vector_store import VectorStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HealthReport:
    database: bool
    vector_store: bool
    llm_configured: bool

    @property
    def ready(self) -> bool:
        return (
            self.database
            and self.vector_store
        )


class ServiceContainer:

    def __init__(
        self,
        settings: Settings,
        embedder: Embedder | None = None,
        vector_store: VectorStore | None = None,
        llm: LLMClient | None = None,
    ) -> None:

        self._settings = settings
        self._embedder_override = embedder
        self._vector_store_override = vector_store
        self._llm_override = llm

    @property
    def settings(self) -> Settings:
        return self._settings

    @cached_property
    def embedder(self) -> Embedder:

        if self._embedder_override is not None:
            return self._embedder_override

        return build_embedder(
            self._settings.embedding_model,
            self._settings.embedding_batch_size,
        )

    @cached_property
    def vector_store(self) -> VectorStore:

        if self._vector_store_override is not None:
            return self._vector_store_override

        if (
            self._settings.vector_backend
            == "memory"
        ):
            from .vector_store import (
                InMemoryVectorStore,
            )

            return InMemoryVectorStore()

        from .qdrant_store import (
            QdrantVectorStore,
        )

        return QdrantVectorStore(
            host=self._settings.qdrant_host,
            port=self._settings.qdrant_port,
            collection=self._settings.qdrant_collection,
            timeout=(
                self._settings
                .qdrant_timeout_seconds
            ),
        )

    @cached_property
    def index_state(self) -> IndexState:
        return IndexState(
            self._settings.database_path
        )

    @cached_property
    def keyword_index(self) -> KeywordIndex:
        return KeywordIndex(
            self._settings.database_path
        )

    @cached_property
    def repository_store(
        self,
    ) -> RepositoryStore:

        return RepositoryStore(
            root=self._settings.repositories_root,
            max_archive_bytes=(
                self._settings.max_upload_bytes
            ),
            max_extracted_bytes=(
                self._settings.max_extracted_bytes
            ),
            max_entries=(
                self._settings.max_archive_entries
            ),
        )

    @cached_property
    def scanner(self) -> RepositoryScanner:
        return RepositoryScanner(
            ScannerConfig(
                max_file_bytes=(
                    self._settings.max_file_bytes
                ),
                max_files=(
                    self._settings.max_files_per_repository
                ),
            )
        )

    @cached_property
    def llm(self) -> LLMClient:

        if self._llm_override is not None:
            return self._llm_override

        return build_llm(
            provider=self._settings.llm_provider,
            api_key=self._settings.gemini_api_key,
            model=self._settings.gemini_model,
            timeout=(
                self._settings
                .llm_timeout_seconds
            ),
            max_output_tokens=(
                self._settings
                .llm_max_output_tokens
            ),
            ollama_base_url=(
                self._settings
                .ollama_base_url
            ),
            ollama_model=(
                self._settings
                .ollama_model
            ),
        )

    @cached_property
    def ingestion(self) -> IngestionService:
        return IngestionService(
            scanner=self.scanner,
            index_state=self.index_state,
            keyword_index=self.keyword_index,
            vector_store=self.vector_store,
            embedder=self.embedder,
            max_chunk_characters=(
                self._settings
                .max_chunk_characters
            ),
            embedding_batch_size=(
                self._settings
                .embedding_batch_size
            ),
        )

    @cached_property
    def retrieval(self) -> RetrievalService:
        return RetrievalService(
            vector_store=self.vector_store,
            keyword_index=self.keyword_index,
            embedder=self.embedder,
            rrf_k=self._settings.rrf_k,
        )

    @cached_property
    def rag(self) -> RagService:
        return RagService(
            retrieval=self.retrieval,
            llm=self.llm,
            max_context_characters=(
                self._settings
                .max_context_characters
            ),
        )

    def startup(self) -> None:

        self.repository_store.initialize()
        self.index_state.initialize()
        self.keyword_index.initialize()

        try:
            self.vector_store.ensure_collection(
                self.embedder.dimension
            )
        except Exception:
            logger.warning(
                "could not prepare vector collection",
                exc_info=True,
            )

    def health(self) -> HealthReport:

        return HealthReport(
            database=(
                self.index_state.health_check()
            ),
            vector_store=(
                self.vector_store.health_check()
            ),
            llm_configured=(
                self._settings.llm_enabled
            ),
        )


def build_container(
    settings: Settings | None = None,
) -> ServiceContainer:

    return ServiceContainer(
        settings or Settings.from_env()
    )