import type { IndexingState } from "../../hooks/useIndexing";
import type { Investigation } from "../../hooks/useInvestigations";
import type { RepositoriesHandle, RepositoryStatusHandle } from "../../hooks/useRepositories";
import { formatAbsoluteTime, formatBytes, formatNumber, formatRelativeTime } from "../../lib/format";
import type { RepoIndexState, RepositorySummary } from "../../types/api";
import { Button } from "../ui/Button";
import { RepositorySwitcher } from "./RepositorySwitcher";
import "./repository.css";

const STATUS_LABEL: Record<RepoIndexState, string> = {
  indexed: "Indexed",
  indexing: "Indexing",
  failed: "Index failed",
  not_indexed: "Not indexed",
  unknown: "Status unknown",
};

interface RepositoryRailProps {
  repos: RepositoriesHandle;
  status: RepositoryStatusHandle;
  indexing: IndexingState;
  history: Investigation[];
  activeInvestigationId: string | null;
  onOpenInvestigation: (id: string) => void;
  onUploadNew: () => void;
  onReindex: (id: string, force?: boolean) => void;
  onDelete: (id: string) => void;
  onSelectRepository: (id: string) => void;
}

export function RepositoryRail({
  repos,
  status,
  indexing,
  history,
  activeInvestigationId,
  onOpenInvestigation,
  onUploadNew,
  onReindex,
  onDelete,
  onSelectRepository,
}: RepositoryRailProps) {
  const selected = repos.selected;
  const detail: RepositorySummary | null = selected ? { ...selected, ...stripNulls(status.status, selected) } : null;
  const indexingThis = indexing.phase === "running" && indexing.repositoryId === selected?.id;
  const state: RepoIndexState = indexingThis ? "indexing" : detail?.status ?? "unknown";
  const maxLang = Math.max(1, ...(detail?.languages.map((l) => l.count ?? 0) ?? [1]));

  return (
    <nav className="rail" aria-label="Repository">
      <div className="rail__section">
        <RepositorySwitcher
          repositories={repos.repositories}
          selected={selected}
          onSelect={onSelectRepository}
          onUploadNew={onUploadNew}
          refreshing={repos.refreshing}
          onRefresh={() => void repos.reload()}
        />
      </div>

      {repos.loadState === "loading" ? (
        <div className="rail__section rail__skeleton" aria-busy="true" aria-label="Loading repositories">
          <span className="skeleton" />
          <span className="skeleton" />
          <span className="skeleton" />
        </div>
      ) : null}

      {detail ? (
        <section className="rail__section" aria-label="Index">
          <div className="rail__heading">
            <h2>Index</h2>
            <span className={`rail__state is-${state}`}>
              <span className={`dot dot--${state}`} aria-hidden="true" />
              {STATUS_LABEL[state]}
            </span>
          </div>
          <dl className="rail__stats">
            <div>
              <dt>Files</dt>
              <dd className="mono">{formatNumber(detail.file_count ?? detail.stored_file_count)}</dd>
            </div>
            <div>
              <dt>Chunks</dt>
              <dd className="mono">{formatNumber(detail.chunk_count)}</dd>
            </div>
            <div>
              <dt>Size</dt>
              <dd className="mono">{formatBytes(detail.size_bytes)}</dd>
            </div>
            <div className="rail__stat-wide">
              <dt>Last indexed</dt>
              <dd title={formatAbsoluteTime(detail.indexed_at)}>{formatRelativeTime(detail.indexed_at)}</dd>
            </div>
          </dl>
          {status.error ? <p className="rail__error">Status unavailable: {status.error.message}</p> : null}

          {detail.languages.length ? (
            <div className="rail__langs">
              <h3>Languages</h3>
              <ul>
                {detail.languages.slice(0, 6).map((l) => (
                  <li key={l.name}>
                    <span className="rail__lang-name">{l.name}</span>
                    {l.count !== null ? (
                      <>
                        <span className="rail__lang-bar" aria-hidden="true">
                          <span style={{ width: `${(l.count / maxLang) * 100}%` }} />
                        </span>
                        <span className="mono rail__lang-count">{formatNumber(l.count)}</span>
                      </>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="rail__actions">
            <Button size="sm" icon="scan" disabled={indexing.phase === "running"} onClick={() => onReindex(detail.id)}>
              {state === "indexed" ? "Re-index" : "Index now"}
            </Button>
            {state === "indexed" ? (
              <Button
                size="sm"
                variant="ghost"
                icon="refresh"
                disabled={indexing.phase === "running"}
                onClick={() => onReindex(detail.id, true)}
                title="Discard existing state and rebuild from scratch"
              >
                Rebuild
              </Button>
            ) : null}
            <Button
              size="sm"
              variant="ghost"
              icon="trash"
              disabled={indexing.phase === "running"}
              onClick={() => onDelete(detail.id)}
            >
              Delete
            </Button>
          </div>
        </section>
      ) : null}

      {selected && history.length ? (
        <section className="rail__section rail__history" aria-label="Questions this session">
          <h2>This session</h2>
          <ul>
            {history.map((inv) => (
              <li key={inv.id}>
                <button
                  type="button"
                  className={inv.id === activeInvestigationId ? "is-active" : undefined}
                  aria-current={inv.id === activeInvestigationId || undefined}
                  onClick={() => onOpenInvestigation(inv.id)}
                >
                  <span className={`rail__hist-dot is-${historyTone(inv)}`} aria-hidden="true" />
                  <span className="rail__hist-q">{inv.question}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <div className="rail__foot">
        <span>Reads repository files. Never executes them.</span>
      </div>
    </nav>
  );
}

function historyTone(inv: Investigation): string {
  if (inv.result.status === "loading") return "loading";
  if (inv.result.status === "error") return "error";
  return inv.result.response.grounded ? "grounded" : "ungrounded";
}

/** Status fields override the list summary only where the status endpoint actually knows the value. */
function stripNulls(status: RepositorySummary | null, base: RepositorySummary): Partial<RepositorySummary> {
  if (!status) return {};
  return {
    status: status.status === "unknown" ? base.status : status.status,
    file_count: status.file_count ?? base.file_count,
    chunk_count: status.chunk_count ?? base.chunk_count,
    stored_file_count: status.stored_file_count ?? base.stored_file_count,
    size_bytes: status.size_bytes ?? base.size_bytes,
    languages: status.languages.length ? status.languages : base.languages,
    indexed_at: status.indexed_at ?? base.indexed_at,
  };
}
