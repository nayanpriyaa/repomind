import type { RetrievalRun } from "../../hooks/useRetrieval";
import { formatDuration, formatLineRange, formatScore, modeLabel, splitPath } from "../../lib/format";
import type { SearchResult } from "../../types/api";
import { ApiErrorNotice } from "../ui/ApiErrorNotice";
import { Icon } from "../ui/Icon";
import "./retrieval.css";

interface RetrievalViewProps {
  run: RetrievalRun | null;
  selectedIndex: number | null;
  onSelect: (index: number) => void;
  onRetry: () => void;
}

export function RetrievalView({ run, selectedIndex, onSelect, onRetry }: RetrievalViewProps) {
  if (!run) {
    return (
      <div className="retrieval-intro">
        <Icon name="list" size={18} />
        <div>
          <h2>Inspect raw retrieval</h2>
          <p>
            Runs <code className="mono">/repositories/search</code> without answer generation. Use it to see which chunks each mode
            ranks, and why an answer did or didn't have evidence.
          </p>
        </div>
      </div>
    );
  }

  const { result } = run;
  return (
    <section className="retrieval" aria-live="polite" aria-busy={result.status === "loading"}>
      <header className="retrieval__head">
        <h2>Retrieval results</h2>
        <p>
          <span className="mono">"{run.query}"</span>
          <span>{modeLabel(run.mode)}</span>
          <span>top {run.topK}</span>
          {result.status === "done" ? <span>{formatDuration(result.durationMs)}</span> : null}
        </p>
      </header>

      {result.status === "loading" ? (
        <div className="retrieval__loading" aria-hidden="true">
          {Array.from({ length: 5 }, (_, i) => (
            <span key={i} className="skeleton" />
          ))}
        </div>
      ) : null}

      {result.status === "error" ? <ApiErrorNotice title="Unable to search repository" error={result.error} onRetry={onRetry} /> : null}

      {result.status === "done" && result.response.results.length === 0 ? (
        <p className="retrieval__none">No chunks matched. Try another mode or a more specific identifier.</p>
      ) : null}

      {result.status === "done" && result.response.results.length > 0 ? (
        <ResultsTable results={result.response.results} selectedIndex={selectedIndex} onSelect={onSelect} />
      ) : null}
    </section>
  );
}

function ResultsTable({ results, selectedIndex, onSelect }: { results: SearchResult[]; selectedIndex: number | null; onSelect: (i: number) => void }) {
  const maxScore = Math.max(...results.map((r) => r.score ?? 0), Number.EPSILON);
  const hasBackendRanks = results.some((r) => r.backend_ranks.semantic !== null || r.backend_ranks.keyword !== null);
  const hasContent = results.some((r) => r.content !== null);
  return (
    <>
      <div className="results" role="table" aria-label="Ranked retrieval results">
        <div className={`results__row results__row--head${hasBackendRanks ? " has-ranks" : ""}`} role="row">
          <span role="columnheader">#</span>
          <span role="columnheader">Chunk</span>
          <span role="columnheader">Match</span>
          {hasBackendRanks ? <span role="columnheader" title="Rank within each retriever before fusion">Sem / Kw</span> : null}
          <span role="columnheader">Score</span>
        </div>
        {results.map((r, i) => {
          const { dir, base } = splitPath(r.file_path);
          return (
            <div
              key={`${r.file_path}:${r.start_line}:${i}`}
              role="row"
              tabIndex={0}
              aria-selected={selectedIndex === i}
              className={`results__row${selectedIndex === i ? " is-selected" : ""}${hasBackendRanks ? " has-ranks" : ""}`}
              onClick={() => onSelect(i)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(i);
                }
              }}
            >
              <span role="cell" className="mono results__rank">{r.rank}</span>
              <span role="cell" className="results__chunk">
                <span className="mono results__path">
                  <span className="results__dir">{dir}</span>
                  {base}
                  <span className="results__lines">:{formatLineRange(r.start_line, r.end_line)}</span>
                </span>
                <span className="results__sub">
                  <span className="mono results__symbol">{r.symbol ?? "—"}</span>
                  {r.chunk_type ? <span>{r.chunk_type}</span> : null}
                  {r.language ? <span>{r.language}</span> : null}
                </span>
              </span>
              <span role="cell" className="results__match">{r.match_type ? modeLabel(r.match_type) : "—"}</span>
              {hasBackendRanks ? (
                <span role="cell" className="mono results__ranks">
                  {r.backend_ranks.semantic ?? "–"} / {r.backend_ranks.keyword ?? "–"}
                </span>
              ) : null}
              <span role="cell" className="results__score">
                <span className="mono">{formatScore(r.score)}</span>
                <span className="results__bar" aria-hidden="true">
                  <span style={{ width: `${Math.max(2, ((r.score ?? 0) / maxScore) * 100)}%` }} />
                </span>
              </span>
            </div>
          );
        })}
      </div>
      {!hasContent ? <p className="retrieval__none">This API response doesn't include chunk text, so the evidence panel shows locations only.</p> : null}
    </>
  );
}
