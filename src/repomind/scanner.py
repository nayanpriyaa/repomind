import os
from pathlib import Path

from repomind.models import CodeFile


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


EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".h": "cpp",
    ".java": "java",
    ".js": "javascript",
    ".ts": "typescript",
}


def scan_repository(repository_path: str) -> list[CodeFile]:
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

            if path.suffix not in SUPPORTED_EXTENSIONS:
                continue

            code_file = CodeFile(
                path=path,
                language=EXTENSION_TO_LANGUAGE[path.suffix],
                size=path.stat().st_size,
            )

            results.append(code_file)

    return results