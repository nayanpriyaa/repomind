"""Shared pytest fixtures.

Every fixture here is offline: the vector store is in-memory and the embedder is
the deterministic hashing encoder, so the suite runs with no Qdrant server, no
model download and no API key.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from repomind.config import Settings
from repomind.container import ServiceContainer
from repomind.embeddings import HashingEmbedder
from repomind.index_state import IndexState
from repomind.keyword_search import KeywordIndex
from repomind.llm import LLMClient
from repomind.models import ChunkType, CodeChunk, Language, SourceFile
from repomind.vector_store import InMemoryVectorStore

PYTHON_SAMPLE = '''"""Authentication helpers."""

import hashlib

ROUNDS = 100000


class TokenService:
    """Issues and validates session tokens."""

    algorithm = "sha256"

    def __init__(self, secret: str) -> None:
        self.secret = secret

    def issue(self, user_id: str) -> str:
        """Create a signed session token."""
        return hashlib.sha256((user_id + self.secret).encode()).hexdigest()

    async def validate(self, token: str) -> bool:
        """Check that a token is well formed."""
        return len(token) == 64


def authenticate(username: str, password: str) -> bool:
    """Verify a username and password pair."""
    return bool(username) and bool(password)
'''

MARKDOWN_SAMPLE = """# Project

Some introduction text that is long enough to survive filtering.

## Installation

Run the installer and wait for it to finish successfully.

## Usage

Call the authenticate function with a username and a password.
"""


class StubLLM:
    """Records the prompts it receives and returns a fixed answer."""

    def __init__(self, response: str = "Authentication lives in app/auth.py:1-10.") -> None:
        self.response = response
        self.system_prompts: list[str] = []
        self.user_prompts: list[str] = []

    @property
    def model(self) -> str:
        return "stub"

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.system_prompts.append(system_prompt)
        self.user_prompts.append(user_prompt)
        return self.response


def write_sample_repository(root: Path) -> Path:
    """Materialise a small repository covering the scanner's edge cases."""
    repository = root / "sample"
    (repository / "app").mkdir(parents=True)
    (repository / ".git").mkdir()
    (repository / "node_modules").mkdir()

    (repository / "app" / "auth.py").write_text(PYTHON_SAMPLE, encoding="utf-8")
    (repository / "README.md").write_text(MARKDOWN_SAMPLE, encoding="utf-8")
    (repository / "app" / "broken.py").write_text("def nope(:\n  ???\n", encoding="utf-8")
    (repository / ".env").write_text("GEMINI_API_KEY=secret\n", encoding="utf-8")
    (repository / "app" / "blob.py").write_bytes(b"def a():\n    pass\x00\x00\x00binary")
    (repository / "app" / "latin.py").write_bytes("def caf\u00e9(): pass".encode("latin-1"))
    (repository / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (repository / "node_modules" / "pkg.js").write_text("module.exports = 1;\n", encoding="utf-8")
    return repository


@pytest.fixture()
def sample_repository(tmp_path: Path) -> Path:
    return write_sample_repository(tmp_path)


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
        repositories_root=tmp_path,
        database_path=tmp_path / "state" / "repomind.db",
        embedding_model="hashing",
        gemini_api_key="",
    )


@pytest.fixture()
def index_state(settings: Settings) -> IndexState:
    state = IndexState(settings.database_path)
    state.initialize()
    return state


@pytest.fixture()
def keyword_index(settings: Settings) -> KeywordIndex:
    index = KeywordIndex(settings.database_path)
    index.initialize()
    return index


@pytest.fixture()
def stub_llm() -> StubLLM:
    return StubLLM()


@pytest.fixture()
def container(settings: Settings, stub_llm: LLMClient) -> ServiceContainer:
    built = ServiceContainer(
        settings,
        embedder=HashingEmbedder(),
        vector_store=InMemoryVectorStore(),
        llm=stub_llm,
    )
    built.startup()
    return built


def make_source(
    content: str,
    file_path: str = "app/auth.py",
    language: Language = Language.PYTHON,
    repository_path: str = "/repositories/sample",
) -> SourceFile:
    """Build a :class:`SourceFile` without touching disk."""
    from repomind.file_hash import hash_text

    return SourceFile(
        repository_path=repository_path,
        file_path=file_path,
        absolute_path=f"{repository_path}/{file_path}",
        language=language,
        size_bytes=len(content.encode("utf-8")),
        sha256=hash_text(content),
        content=content,
    )


def make_chunk(
    chunk_id: str,
    symbol: str = "example",
    file_path: str = "app/auth.py",
    content: str = "def example():\n    return True\n",
    start_line: int = 1,
    end_line: int = 2,
    repository_path: str = "/repositories/sample",
) -> CodeChunk:
    """Build a :class:`CodeChunk` directly, bypassing the parser."""
    return CodeChunk(
        chunk_id=chunk_id,
        repository_path=repository_path,
        file_path=file_path,
        language=Language.PYTHON,
        chunk_type=ChunkType.FUNCTION,
        symbol=symbol,
        start_line=start_line,
        end_line=end_line,
        content=content,
    )
