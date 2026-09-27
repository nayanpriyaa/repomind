"""Command-line entry point: ``python -m repomind <command>``.

Exists so the pipeline can be driven without the HTTP layer, which matters for
batch indexing, for the evaluation harness and for debugging retrieval without a
browser in the loop.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys

from .config import RepositoryAccessError, Settings, configure_logging
from .container import build_container
from .models import SearchMode
from .retrieval import RetrievalRequest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="repomind", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    index = subparsers.add_parser("index", help="index or re-index a repository")
    index.add_argument("repository")
    index.add_argument("--force", action="store_true", help="rebuild from scratch")

    query = subparsers.add_parser("query", help="ask a question about a repository")
    query.add_argument("repository")
    query.add_argument("question")
    query.add_argument("--top-k", type=int, default=5)
    query.add_argument(
        "--mode", choices=[mode.value for mode in SearchMode], default="hybrid"
    )

    search = subparsers.add_parser("search", help="retrieval only, no generation")
    search.add_argument("repository")
    search.add_argument("query")
    search.add_argument("--top-k", type=int, default=10)
    search.add_argument(
        "--mode", choices=[mode.value for mode in SearchMode], default="hybrid"
    )

    status = subparsers.add_parser("status", help="show indexing status")
    status.add_argument("repository", nargs="?")

    serve = subparsers.add_parser("serve", help="run the HTTP API")
    serve.add_argument("--host", default="0.0.0.0")  # noqa: S104 - container default
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.from_env()
    configure_logging(settings.log_level)

    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "repomind.api.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
        return 0

    container = build_container(settings)

    if args.command == "status" and not args.repository:
        print(
            json.dumps(
                [dataclasses.asdict(item) for item in container.index_state.list_repositories()],
                indent=2,
                default=str,
            )
        )
        return 0

    try:
        repository = str(settings.resolve_repository_path(args.repository))
    except RepositoryAccessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.command == "index":
        report = container.ingestion.index_repository(repository, force=args.force)
        print(
            f"indexed {report.files_indexed} files "
            f"({report.files_unchanged} unchanged, {report.files_deleted} deleted), "
            f"{report.chunks_indexed} chunks in {report.duration_seconds:.2f}s"
        )
        return 0

    if args.command == "status":
        print(json.dumps(dataclasses.asdict(container.index_state.status(repository)), indent=2, default=str))
        return 0

    if args.command == "search":
        hits = container.retrieval.search(
            RetrievalRequest(
                query=args.query,
                mode=SearchMode(args.mode),
                top_k=args.top_k,
                repository_path=repository,
            )
        )
        for position, hit in enumerate(hits, start=1):
            print(f"{position:2d}. {hit.location}  {hit.symbol}  ({hit.score:.4f})")
        return 0

    if args.command == "query":
        answer = container.rag.answer(
            question=args.question,
            repository_path=repository,
            top_k=args.top_k,
            mode=SearchMode(args.mode),
        )
        print(answer.answer)
        print("\nSources:")
        for citation in answer.citations:
            print(f"  {citation.file_path}:{citation.start_line}-{citation.end_line}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
