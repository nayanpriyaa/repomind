from dataclasses import dataclass
from pathlib import Path


@dataclass
class CodeFile:
    path: Path
    language: str
    size: int


@dataclass
class CodeChunk:
    file_path: Path
    chunk_type: str
    name: str
    start_line: int
    end_line: int
    content: str