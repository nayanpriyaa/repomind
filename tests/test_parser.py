from pathlib import Path
from tempfile import TemporaryDirectory

from repomind.parser import parse_python_file


def test_parse_function():
    with TemporaryDirectory() as temp_dir:
        file_path = Path(temp_dir) / "sample.py"

        file_path.write_text(
            """
def hello(name):
    return f"Hello {name}"
""".strip(),
            encoding="utf-8",
        )

        chunks = parse_python_file(file_path)

        assert len(chunks) == 1

        chunk = chunks[0]

        assert chunk.chunk_type == "FUNCTION"
        assert chunk.name == "hello"
        assert chunk.start_line == 1
        assert chunk.end_line == 2
        assert "return f" in chunk.content


def test_parse_class_and_methods():
    with TemporaryDirectory() as temp_dir:
        file_path = Path(temp_dir) / "sample.py"

        file_path.write_text(
            """
class UserService:

    def authenticate(self, username, password):
        return True

    def logout(self):
        print("Logged out")
""".strip(),
            encoding="utf-8",
        )

        chunks = parse_python_file(file_path)

        assert len(chunks) == 3

        assert chunks[0].chunk_type == "CLASS"
        assert chunks[0].name == "UserService"

        assert chunks[1].chunk_type == "METHOD"
        assert chunks[1].name == "authenticate"

        assert chunks[2].chunk_type == "METHOD"
        assert chunks[2].name == "logout"


def test_decorator_is_included_in_start_line():
    with TemporaryDirectory() as temp_dir:
        file_path = Path(temp_dir) / "sample.py"

        file_path.write_text(
            """
from dataclasses import dataclass


@dataclass
class User:
    name: str
""".strip(),
            encoding="utf-8",
        )

        chunks = parse_python_file(file_path)

        assert len(chunks) == 1

        chunk = chunks[0]

        assert chunk.chunk_type == "CLASS"
        assert chunk.name == "User"

        # @dataclass is line 4, class User is line 5.
        assert chunk.start_line == 4
        assert chunk.end_line == 6

        assert "@dataclass" in chunk.content


def test_async_function():
    with TemporaryDirectory() as temp_dir:
        file_path = Path(temp_dir) / "sample.py"

        file_path.write_text(
            """
async def fetch_data():
    return "data"
""".strip(),
            encoding="utf-8",
        )

        chunks = parse_python_file(file_path)

        assert len(chunks) == 1

        chunk = chunks[0]

        assert chunk.chunk_type == "FUNCTION"
        assert chunk.name == "fetch_data"