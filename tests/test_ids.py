from repomind.ids import generate_chunk_id


def test_same_chunk_generates_same_id():
    first_id = generate_chunk_id(
        repository_path="repo",
        file_path="service.py",
        chunk_type="METHOD",
        name="authenticate",
        start_line=10,
        end_line=20,
    )

    second_id = generate_chunk_id(
        repository_path="repo",
        file_path="service.py",
        chunk_type="METHOD",
        name="authenticate",
        start_line=10,
        end_line=20,
    )

    assert first_id == second_id


def test_different_chunks_generate_different_ids():
    first_id = generate_chunk_id(
        repository_path="repo",
        file_path="service.py",
        chunk_type="METHOD",
        name="authenticate",
        start_line=10,
        end_line=20,
    )

    second_id = generate_chunk_id(
        repository_path="repo",
        file_path="service.py",
        chunk_type="METHOD",
        name="logout",
        start_line=30,
        end_line=35,
    )

    assert first_id != second_id