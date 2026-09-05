from pathlib import Path


def scan_repository(repository_path: str) -> list[Path]:
    root = Path(repository_path)

    if not root.exists():
        raise FileNotFoundError(f"Repository does not exist: {root}")

    if not root.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {root}")

    return [
        path
        for path in root.rglob("*")
        if path.is_file()
    ]