"""Embedding abstraction: laziness and batching."""

from __future__ import annotations

from repomind.embeddings import (
    DEFAULT_MODEL,
    HashingEmbedder,
    SentenceTransformerEmbedder,
    build_embedder,
    iter_batches,
)


def test_sentence_transformer_does_not_load_on_construction() -> None:
    embedder = SentenceTransformerEmbedder(DEFAULT_MODEL)
    assert embedder.is_loaded is False


def test_known_model_dimension_needs_no_download() -> None:
    assert SentenceTransformerEmbedder(DEFAULT_MODEL).dimension == 384
    assert SentenceTransformerEmbedder(DEFAULT_MODEL).is_loaded is False


def test_build_embedder_selects_the_offline_encoder() -> None:
    assert isinstance(build_embedder("hashing"), HashingEmbedder)


def test_build_embedder_defaults_to_sentence_transformers() -> None:
    assert isinstance(build_embedder(DEFAULT_MODEL), SentenceTransformerEmbedder)


def test_hashing_embedder_is_deterministic() -> None:
    embedder = HashingEmbedder()
    assert embedder.embed_query("def authenticate(user)") == embedder.embed_query("def authenticate(user)")


def test_hashing_embedder_produces_unit_vectors() -> None:
    import math

    vector = HashingEmbedder().embed_query("token service issue")
    assert abs(math.sqrt(sum(value * value for value in vector)) - 1.0) < 1e-9


def test_hashing_embedder_separates_unrelated_text() -> None:
    embedder = HashingEmbedder()
    left = embedder.embed_query("authenticate password login")
    right = embedder.embed_query("matrix determinant eigenvalue")
    assert sum(a * b for a, b in zip(left, right)) < 0.5


def test_embed_documents_matches_embed_query() -> None:
    embedder = HashingEmbedder()
    assert embedder.embed_documents(["abc"])[0] == embedder.embed_query("abc")


def test_embed_documents_handles_an_empty_batch() -> None:
    assert HashingEmbedder().embed_documents([]) == []


def test_iter_batches_covers_every_item() -> None:
    items = [str(i) for i in range(10)]
    batches = list(iter_batches(items, 3))
    assert [len(batch) for batch in batches] == [3, 3, 3, 1]
    assert [item for batch in batches for item in batch] == items
