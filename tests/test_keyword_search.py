from pathlib import Path

from repomind.keyword_search import keyword_score
from repomind.models import CodeChunk


def create_chunk(
    name: str,
    content: str,
) -> CodeChunk:
    return CodeChunk(
        file_path=Path("test.py"),
        chunk_type="FUNCTION",
        name=name,
        start_line=1,
        end_line=5,
        content=content,
    )


def test_exact_keyword_match():
    chunk = create_chunk(
        name="authenticate",
        content="def authenticate(): return True",
    )

    score = keyword_score(
        query="authenticate",
        chunk=chunk,
    )

    assert score == 1.0


def test_partial_keyword_match():
    chunk = create_chunk(
        name="authenticate",
        content="def authenticate(): return True",
    )

    score = keyword_score(
        query="authenticate user",
        chunk=chunk,
    )

    assert score == 0.5


def test_no_keyword_match():
    chunk = create_chunk(
        name="calculate_total",
        content="return price * quantity",
    )

    score = keyword_score(
        query="authenticate",
        chunk=chunk,
    )

    assert score == 0.0


def test_keyword_matching_is_case_insensitive():
    chunk = create_chunk(
        name="authenticate",
        content="OPENAI_API_KEY = settings.OPENAI_API_KEY",
    )

    score = keyword_score(
        query="openai api key",
        chunk=chunk,
    )

    assert score == 1.0