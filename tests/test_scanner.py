from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from repomind.scanner import scan_repository


def test_scan_repository():
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)

        # Supported source file
        (root / "main.py").touch()

        # Unsupported file
        (root / "image.png").touch()

        # Supported file inside an ignored directory
        venv_dir = root / ".venv"
        venv_dir.mkdir()
        (venv_dir / "fake.py").touch()

        results = scan_repository(str(root))

        assert results == [root / "main.py"]


def test_scan_repository_nonexistent_path():
    with pytest.raises(FileNotFoundError):
        scan_repository("this_directory_does_not_exist")


def test_scan_repository_file_instead_of_directory():
    with TemporaryDirectory() as temp_dir:
        file_path = Path(temp_dir) / "file.py"
        file_path.touch()

        with pytest.raises(NotADirectoryError):
            scan_repository(str(file_path))