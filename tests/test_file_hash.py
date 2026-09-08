from pathlib import Path
from tempfile import TemporaryDirectory

from repomind.file_hash import calculate_file_hash


def test_same_file_produces_same_hash():
    with TemporaryDirectory() as temp_dir:
        file_path = Path(temp_dir) / "main.py"
        file_path.write_text("print('hello')")

        hash_one = calculate_file_hash(file_path)
        hash_two = calculate_file_hash(file_path)

        assert hash_one == hash_two


def test_changed_file_produces_different_hash():
    with TemporaryDirectory() as temp_dir:
        file_path = Path(temp_dir) / "main.py"

        file_path.write_text("print('hello')")
        hash_one = calculate_file_hash(file_path)

        file_path.write_text("print('hello world')")
        hash_two = calculate_file_hash(file_path)

        assert hash_one != hash_two