import os
from pathlib import Path


SUPPORTED_EXTENSIONS = {
    ".py",
    ".cpp",
    ".hpp",
    ".h",
    ".java",
    ".js",
    ".ts",
}

IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "build",
    "dist",
}


def scan_repository(repository_path: str) -> list[Path]:
    root = Path(repository_path)

    if not root.exists():
        raise FileNotFoundError(f"Repository does not exist: {root}")

    if not root.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {root}")

    results = []

    for current_dir, directories, files in os.walk(root):
        directories[:] = [
            directory
            for directory in directories
            if directory not in IGNORED_DIRECTORIES
        ]

        for filename in files:
            path = Path(current_dir) / filename

            if path.suffix in SUPPORTED_EXTENSIONS:
                results.append(path)

    return results