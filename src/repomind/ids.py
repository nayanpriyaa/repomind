import hashlib


def generate_chunk_id(
    repository_path: str,
    file_path: str,
    chunk_type: str,
    name: str,
    start_line: int,
    end_line: int,
) -> int:
    identity = (
        f"{repository_path}|"
        f"{file_path}|"
        f"{chunk_type}|"
        f"{name}|"
        f"{start_line}|"
        f"{end_line}"
    )

    digest = hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()

    return int(digest[:15], 16)