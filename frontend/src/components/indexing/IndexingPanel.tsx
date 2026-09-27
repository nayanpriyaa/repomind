import type { IndexingState } from "../../hooks/useIndexing";
import { useElapsed } from "../../hooks/useElapsed";
import { formatDuration, formatNumber } from "../../lib/format";
import type { HealthReport, RepositoryStatus } from "../../types/api";
import { ApiErrorNotice } from "../ui/ApiErrorNotice";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import "./indexing.css";

interface IndexingPanelProps {
  state: Exclude<IndexingState, { phase: "idle" }>;
  health: HealthReport | null;
  onRetry: () => void;
  onDismiss: () => void;
}

export function IndexingPanel({ state, health, onRetry, onDismiss }: IndexingPanelProps) {
  const running = state.phase === "running";
  const elapsed = useElapsed(state.startedAt, running);
  const duration = running ? elapsed : state.finishedAt - state.startedAt;
  const snapshot: RepositoryStatus | null = state.phase === "succeeded" ? state.result : state.latest;
  const progress = snapshot?.progress ?? null;
  const pct =
    progress && progress.files_processed !== null && progress.files_total
      ? Math.min(100, Math.round((progress.files_processed / progress.files_total) * 100))
      : null;

  const title = running ? "Indexing repository" : state.phase === "succeeded" ? "Repository indexed" : "Indexing failed";

  return (
    <section className={`indexing is-${state.phase}`} aria-live="polite" aria-busy={running}>
      <header className="indexing__head">
        <span className="indexing__icon" aria-hidden="true">
          {running ? <span className="spinner" /> : <Icon name={state.phase === "succeeded" ? "checkCircle" : "alert"} size={18} />}
        </span>
        <div>
          <h1>{title}</h1>
          <p className="mono indexing__path">{state.repositoryId}</p>
        </div>
        <span className="indexing__elapsed mono" aria-label={`Elapsed ${formatDuration(duration)}`}>
          {formatDuration(duration)}
        </span>
      </header>

      <div
        className={`indexing__track${pct === null && running ? " is-indeterminate" : ""}`}
        role="progressbar"
        aria-label="Indexing progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct ?? (state.phase === "succeeded" ? 100 : undefined)}
      >
        <span style={{ width: pct !== null ? `${pct}%` : state.phase === "succeeded" ? "100%" : undefined }} />
      </div>

      {running ? (
        <p className="indexing__note">
          {pct !== null
            ? `${pct}% of discovered files processed`
            : "The API doesn't report incremental progress for this run. Stats appear as the status endpoint reports them."}
        </p>
      ) : null}

      {progress?.current_file && running ? (
        <p className="indexing__current">
          Processing <span className="mono">{progress.current_file}</span>
        </p>
      ) : null}

      <dl className="indexing__stats">
        <div>
          <dt>Files</dt>
          <dd className="mono">
            {progress?.files_processed !== null && progress?.files_processed !== undefined
              ? `${formatNumber(progress.files_processed)}${progress.files_total !== null ? ` / ${formatNumber(progress.files_total)}` : ""}`
              : formatNumber(snapshot?.file_count)}
          </dd>
        </div>
        <div>
          <dt>Chunks</dt>
          <dd className="mono">{formatNumber(snapshot?.chunk_count)}</dd>
        </div>
        <div className="indexing__stat-wide">
          <dt>Languages</dt>
          <dd>{snapshot?.languages.length ? snapshot.languages.map((l) => l.name).join(", ") : "—"}</dd>
        </div>
      </dl>

      {health && health.checks.length > 0 ? (
        <div className="indexing__services">
          <h2>Services</h2>
          <ul>
            {health.checks.map((c) => (
              <li key={c.name}>
                <span className={`dot dot--${c.state}`} aria-hidden="true" />
                <span className="mono">{c.name}</span>
                <span className={`indexing__svc-state is-${c.state}`}>{c.state === "ready" ? "Ready" : c.detail ?? c.state}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {state.phase === "failed" ? (
        <ApiErrorNotice
          title="The index request did not complete"
          error={state.error}
          hints={[
            "the repository still exists on the server",
            "Qdrant and the embedding service are ready",
            "the archive actually contained source files",
          ]}
        />
      ) : null}

      <div className="indexing__actions">
        {state.phase === "failed" ? (
          <>
            <Button variant="primary" icon="refresh" onClick={onRetry}>Retry indexing</Button>
            <Button variant="ghost" onClick={onDismiss}>Dismiss</Button>
          </>
        ) : null}
        {state.phase === "succeeded" ? <Button variant="primary" onClick={onDismiss}>Start asking</Button> : null}
        {running ? <Button variant="ghost" onClick={onDismiss}>Stop watching</Button> : null}
      </div>
    </section>
  );
}
