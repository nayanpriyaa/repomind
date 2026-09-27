"""Runtime configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5-coder:7b"


class ConfigurationError(RuntimeError):
    """Raised when configuration is invalid."""


class RepositoryAccessError(PermissionError):
    """Raised when a repository path escapes the configured root."""


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigurationError(
            f"{name} must be an integer, got {raw!r}"
        ) from exc


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True, slots=True)
class Settings:
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "repomind_chunks"
    qdrant_timeout_seconds: float = 30.0
    vector_backend: str = "qdrant"

    # LLM
    llm_provider: str = "ollama"
    gemini_api_key: str = field(default="", repr=False)
    gemini_model: str = DEFAULT_GEMINI_MODEL

    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL
    ollama_model: str = DEFAULT_OLLAMA_MODEL

    llm_timeout_seconds: float = 120.0
    llm_max_output_tokens: int = 1024

    # Embeddings
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    embedding_batch_size: int = 32

    # Storage
    repositories_root: Path = Path("/repositories")
    database_path: Path = Path("/data/repomind.db")

    # Upload limits
    max_upload_bytes: int = 200 * 1024 * 1024
    max_extracted_bytes: int = 1024 * 1024 * 1024
    max_archive_entries: int = 20_000

    # Existing indexing limits
    max_file_bytes: int = 1_048_576
    max_files_per_repository: int = 20_000
    max_context_characters: int = 24_000
    max_chunk_characters: int = 6_000
    default_top_k: int = 5
    max_top_k: int = 50
    rrf_k: int = 60

    cors_allow_origins: list[str] = field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            qdrant_host=_env_str("QDRANT_HOST", "localhost"),
            qdrant_port=_env_int("QDRANT_PORT", 6333),
            qdrant_collection=_env_str(
                "QDRANT_COLLECTION",
                "repomind_chunks",
            ),
            qdrant_timeout_seconds=float(
                _env_int("QDRANT_TIMEOUT_SECONDS", 30)
            ),
            vector_backend=_env_str(
                "VECTOR_BACKEND",
                "qdrant",
            ).lower(),

            llm_provider=_env_str(
                "LLM_PROVIDER",
                "ollama",
            ).lower(),

            gemini_api_key=_env_str(
                "GEMINI_API_KEY",
                "",
            ),
            gemini_model=_env_str(
                "GEMINI_MODEL",
                DEFAULT_GEMINI_MODEL,
            ),

            ollama_base_url=_env_str(
                "OLLAMA_BASE_URL",
                DEFAULT_OLLAMA_BASE_URL,
            ),
            ollama_model=_env_str(
                "OLLAMA_MODEL",
                DEFAULT_OLLAMA_MODEL,
            ),

            llm_timeout_seconds=float(
                _env_int("LLM_TIMEOUT_SECONDS", 120)
            ),
            llm_max_output_tokens=_env_int(
                "LLM_MAX_OUTPUT_TOKENS",
                1024,
            ),

            embedding_model=_env_str(
                "EMBEDDING_MODEL",
                DEFAULT_EMBEDDING_MODEL,
            ),
            embedding_batch_size=_env_int(
                "EMBEDDING_BATCH_SIZE",
                32,
            ),

            repositories_root=Path(
                _env_str("REPOSITORIES_ROOT", "/repositories")
            ),
            database_path=Path(
                _env_str("DATABASE_PATH", "/data/repomind.db")
            ),

            max_upload_bytes=_env_int(
                "MAX_UPLOAD_BYTES",
                200 * 1024 * 1024,
            ),
            max_extracted_bytes=_env_int(
                "MAX_EXTRACTED_BYTES",
                1024 * 1024 * 1024,
            ),
            max_archive_entries=_env_int(
                "MAX_ARCHIVE_ENTRIES",
                20_000,
            ),

            max_file_bytes=_env_int(
                "MAX_FILE_BYTES",
                1_048_576,
            ),
            max_files_per_repository=_env_int(
                "MAX_FILES_PER_REPOSITORY",
                100_000,
            ),
            max_context_characters=_env_int(
                "MAX_CONTEXT_CHARACTERS",
                24_000,
            ),
            max_chunk_characters=_env_int(
                "MAX_CHUNK_CHARACTERS",
                6_000,
            ),
            default_top_k=_env_int(
                "DEFAULT_TOP_K",
                5,
            ),
            max_top_k=_env_int(
                "MAX_TOP_K",
                50,
            ),
            rrf_k=_env_int(
                "RRF_K",
                60,
            ),

            cors_allow_origins=_env_list(
                "CORS_ALLOW_ORIGINS",
                [
                    "http://localhost:5173",
                    "http://127.0.0.1:5173",
                ],
            ),

            log_level=_env_str(
                "LOG_LEVEL",
                "INFO",
            ).upper(),
        )

    @property
    def llm_enabled(self) -> bool:
        if self.llm_provider == "ollama":
            return bool(self.ollama_model)

        if self.llm_provider == "gemini":
            return bool(self.gemini_api_key)

        return False

    @property
    def qdrant_url(self) -> str:
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

    def resolve_repository_path(
        self,
        requested: str | os.PathLike[str],
    ) -> Path:
        root = self.repositories_root.expanduser().resolve()

        candidate = Path(requested).expanduser()

        if not candidate.is_absolute():
            candidate = root / candidate

        resolved = candidate.resolve()

        if resolved != root and root not in resolved.parents:
            raise RepositoryAccessError(
                "repository path is outside the configured repositories root"
            )

        if not resolved.is_dir():
            raise RepositoryAccessError(
                "repository path is not an existing directory"
            )

        return resolved


def configure_logging(level: str = "INFO") -> None:
    import logging

    root = logging.getLogger()

    if root.handlers:
        root.setLevel(level)
        return

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )