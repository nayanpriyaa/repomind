from pathlib import Path
from tempfile import TemporaryDirectory

from repomind.ingestion import ingest_repository


def test_ingest_repository():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        python_file = root / "service.py"

        python_file.write_text(
            """
class UserService:

    def authenticate(self, username, password):
        return True


def health_check():
    return "OK"
""".strip(),
            encoding="utf-8",
        )

        chunks = ingest_repository(str(root))

        assert len(chunks) == 3

        assert chunks[0].chunk_type == "CLASS"
        assert chunks[0].name == "UserService"

        assert chunks[1].chunk_type == "METHOD"
        assert chunks[1].name == "authenticate"

        assert chunks[2].chunk_type == "FUNCTION"
        assert chunks[2].name == "health_check"