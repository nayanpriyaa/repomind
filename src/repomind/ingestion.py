from repomind.models import CodeChunk
from repomind.parser import parse_python_file
from repomind.scanner import scan_repository


def ingest_repository(repository_path: str) -> list[CodeChunk]:
    code_files = scan_repository(repository_path)

    chunks = []

    for code_file in code_files:
        if code_file.language != "python":
            continue

        file_chunks = parse_python_file(code_file.path)
        chunks.extend(file_chunks)

    return chunks