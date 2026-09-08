import re

from repomind.models import CodeChunk


def tokenize(text: str) -> set[str]:
    """
    Convert text into lowercase searchable tokens.

    Normal text:
        "hello world"
        -> {"hello", "world"}

    Code identifiers:
        "OPENAI_API_KEY"
        -> {"openai_api_key", "openai", "api", "key"}
    """

    raw_tokens = re.findall(
        r"[A-Za-z0-9_]+",
        text,
    )

    tokens = set()

    for token in raw_tokens:
        token = token.lower()

        if not token:
            continue

        # Keep the complete identifier.
        tokens.add(token)

        # Also split snake_case identifiers.
        if "_" in token:
            parts = token.split("_")

            for part in parts:
                if part:
                    tokens.add(part)

    return tokens


def keyword_score(
    query: str,
    chunk: CodeChunk,
) -> float:
    """
    Calculate how strongly a query matches a code chunk
    using keyword overlap.
    """

    query_tokens = tokenize(query)

    chunk_text = (
        f"{chunk.name}\n"
        f"{chunk.content}"
    )

    chunk_tokens = tokenize(chunk_text)

    if not query_tokens:
        return 0.0

    matched_tokens = query_tokens & chunk_tokens

    return len(matched_tokens) / len(query_tokens)