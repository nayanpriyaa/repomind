from pathlib import Path

from repomind.parser import parse_python_file


def main() -> None:
    file_path = input("Python file path: ").strip()

    chunks = parse_python_file(Path(file_path))

    print(f"\nFound {len(chunks)} chunks:\n")

    for chunk in chunks:
        print(
            f"[{chunk.chunk_type}] "
            f"{chunk.name} "
            f"(lines {chunk.start_line}-{chunk.end_line})"
        )


if __name__ == "__main__":
    main()