"""Retrieval evaluation harness.

Measures Recall@k, MRR@5, Hit Rate@5 and latency for each retrieval mode against
a hand-written ground-truth set, and separately times full and incremental
indexing.

Relevance is judged at *file* granularity by default. Chunk-level ground truth
would be more precise but is not worth hand-maintaining: for the question this
system answers ("where is X implemented"), landing the user in the right file is
the outcome that matters.

Usage
-----
    python -m evaluation.benchmark \\
        --repository /repositories/example \\
        --queries evaluation/queries.example.json \\
        --output evaluation/results.json

Nothing here fabricates numbers: results are written only for runs that
actually executed.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Sequence

from repomind.config import Settings
from repomind.container import ServiceContainer, build_container
from repomind.models import SearchMode
from repomind.retrieval import RetrievalRequest

DEFAULT_CUTOFFS = (1, 3, 5)


@dataclass(frozen=True, slots=True)
class EvaluationQuery:
    """One labelled question."""

    question: str
    relevant_files: list[str]

    @classmethod
    def from_dict(cls, payload: dict) -> "EvaluationQuery":
        files = payload.get("relevant_files") or []
        if not payload.get("question") or not files:
            raise ValueError("each query needs a 'question' and 'relevant_files'")
        return cls(question=payload["question"], relevant_files=list(files))


@dataclass
class ModeMetrics:
    """Aggregate retrieval quality for one mode."""

    mode: str
    query_count: int = 0
    recall_at: dict[int, float] = field(default_factory=dict)
    mrr_at_5: float = 0.0
    hit_rate_at_5: float = 0.0
    latency_ms_mean: float = 0.0
    latency_ms_p95: float = 0.0


@dataclass
class IndexingMetrics:
    """Timings for the indexing paths."""

    full_index_seconds: float
    full_index_files: int
    full_index_chunks: int
    incremental_noop_seconds: float
    incremental_noop_files_indexed: int
    incremental_noop_files_unchanged: int
    single_file_change_seconds: float
    single_file_change_files_indexed: int


def load_queries(path: str | Path) -> list[EvaluationQuery]:
    """Read the ground-truth file."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = payload["queries"] if isinstance(payload, dict) else payload
    return [EvaluationQuery.from_dict(entry) for entry in entries]


def evaluate_mode(
    container: ServiceContainer,
    repository_path: str,
    queries: Sequence[EvaluationQuery],
    mode: SearchMode,
    cutoffs: Sequence[int] = DEFAULT_CUTOFFS,
    top_k: int = 5,
) -> ModeMetrics:
    """Run every query in one mode and aggregate the metrics."""
    hits_at: dict[int, list[float]] = {cutoff: [] for cutoff in cutoffs}
    reciprocal_ranks: list[float] = []
    latencies: list[float] = []

    for query in queries:
        started = time.perf_counter()
        results = container.retrieval.search(
            RetrievalRequest(
                query=query.question,
                mode=mode,
                top_k=top_k,
                repository_path=repository_path,
            )
        )
        latencies.append((time.perf_counter() - started) * 1000)

        ranked_files = [result.file_path for result in results]
        relevant = set(query.relevant_files)

        for cutoff in cutoffs:
            hits_at[cutoff].append(
                1.0 if relevant.intersection(ranked_files[:cutoff]) else 0.0
            )

        rank = next(
            (
                position
                for position, file_path in enumerate(ranked_files[:5], start=1)
                if file_path in relevant
            ),
            None,
        )
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)

    return ModeMetrics(
        mode=mode.value,
        query_count=len(queries),
        recall_at={
            cutoff: round(statistics.fmean(values), 4) if values else 0.0
            for cutoff, values in hits_at.items()
        },
        mrr_at_5=round(statistics.fmean(reciprocal_ranks), 4) if reciprocal_ranks else 0.0,
        hit_rate_at_5=round(statistics.fmean(hits_at[max(cutoffs)]), 4)
        if hits_at[max(cutoffs)]
        else 0.0,
        latency_ms_mean=round(statistics.fmean(latencies), 2) if latencies else 0.0,
        latency_ms_p95=round(_percentile(latencies, 95), 2) if latencies else 0.0,
    )


def measure_indexing(
    container: ServiceContainer, repository_path: str
) -> IndexingMetrics:
    """Time a full rebuild, a no-op re-run and a single-file change."""
    full = container.ingestion.index_repository(repository_path, force=True)
    noop = container.ingestion.index_repository(repository_path)

    probe = Path(repository_path) / ".repomind_benchmark_probe.py"
    probe.write_text(
        f"# generated by the benchmark at {time.time()}\n"
        "def benchmark_probe():\n    return 'incremental indexing probe'\n",
        encoding="utf-8",
    )
    try:
        single = container.ingestion.index_repository(repository_path)
    finally:
        probe.unlink(missing_ok=True)
        container.ingestion.index_repository(repository_path)

    return IndexingMetrics(
        full_index_seconds=round(full.duration_seconds, 3),
        full_index_files=full.files_indexed,
        full_index_chunks=full.chunks_indexed,
        incremental_noop_seconds=round(noop.duration_seconds, 3),
        incremental_noop_files_indexed=noop.files_indexed,
        incremental_noop_files_unchanged=noop.files_unchanged,
        single_file_change_seconds=round(single.duration_seconds, 3),
        single_file_change_files_indexed=single.files_indexed,
    )


def run(
    repository: str,
    queries_path: str,
    output: str | None,
    top_k: int,
    skip_indexing: bool,
) -> dict:
    """Execute the benchmark and return the report."""
    settings = Settings.from_env()
    container = build_container(settings)
    container.startup()
    repository_path = str(settings.resolve_repository_path(repository))
    queries = load_queries(queries_path)

    indexing = None if skip_indexing else measure_indexing(container, repository_path)
    if skip_indexing:
        container.ingestion.index_repository(repository_path)

    report = {
        "repository_path": repository_path,
        "embedding_model": settings.embedding_model,
        "query_count": len(queries),
        "top_k": top_k,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "indexing": asdict(indexing) if indexing else None,
        "retrieval": [
            asdict(evaluate_mode(container, repository_path, queries, mode, top_k=top_k))
            for mode in (SearchMode.KEYWORD, SearchMode.SEMANTIC, SearchMode.HYBRID)
        ],
    }

    if output:
        Path(output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def render(report: dict) -> str:
    """Format the report as a readable table."""
    lines = [
        f"repository      : {report['repository_path']}",
        f"embedding model : {report['embedding_model']}",
        f"queries         : {report['query_count']}",
        "",
        f"{'mode':10} {'R@1':>7} {'R@3':>7} {'R@5':>7} {'MRR@5':>7} {'Hit@5':>7} "
        f"{'mean ms':>9} {'p95 ms':>8}",
    ]
    for metrics in report["retrieval"]:
        recall = metrics["recall_at"]
        lines.append(
            f"{metrics['mode']:10} "
            f"{recall.get('1', recall.get(1, 0)):>7.3f} "
            f"{recall.get('3', recall.get(3, 0)):>7.3f} "
            f"{recall.get('5', recall.get(5, 0)):>7.3f} "
            f"{metrics['mrr_at_5']:>7.3f} {metrics['hit_rate_at_5']:>7.3f} "
            f"{metrics['latency_ms_mean']:>9.2f} {metrics['latency_ms_p95']:>8.2f}"
        )
    indexing = report.get("indexing")
    if indexing:
        lines += [
            "",
            f"full index      : {indexing['full_index_seconds']}s "
            f"({indexing['full_index_files']} files, {indexing['full_index_chunks']} chunks)",
            f"re-index (no-op): {indexing['incremental_noop_seconds']}s "
            f"({indexing['incremental_noop_files_indexed']} indexed, "
            f"{indexing['incremental_noop_files_unchanged']} unchanged)",
            f"one file changed: {indexing['single_file_change_seconds']}s "
            f"({indexing['single_file_change_files_indexed']} indexed)",
        ]
    return "\n".join(lines)


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(
        len(ordered) - 1, int(round((percentile / 100.0) * (len(ordered) - 1)))
    )
    return ordered[index]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--queries", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--skip-indexing",
        action="store_true",
        help="reuse the existing index instead of timing a rebuild",
    )
    args = parser.parse_args(argv)
    print(render(run(args.repository, args.queries, args.output, args.top_k, args.skip_indexing)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
