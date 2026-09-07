from repomind.similarity import cosine_similarity


def test_identical_vectors():
    similarity = cosine_similarity(
        [1, 0, 0],
        [1, 0, 0],
    )

    assert similarity == 1.0


def test_different_vectors():
    similarity = cosine_similarity(
        [1, 0, 0],
        [0, 1, 0],
    )

    assert similarity == 0.0


def test_zero_vector():
    similarity = cosine_similarity(
        [1, 2, 3],
        [0, 0, 0],
    )

    assert similarity == 0.0