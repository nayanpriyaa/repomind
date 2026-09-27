import { useEffect, useRef, type KeyboardEvent } from "react";
import { formatBytes, formatNumber, formatRelativeTime } from "../../lib/format";
import type { RepositorySummary } from "../../types/api";
import { Icon } from "../ui/Icon";
import { usePopover } from "../ui/usePopover";
import "./repository.css";

interface RepositorySwitcherProps {
  repositories: RepositorySummary[];
  selected: RepositorySummary | null;
  onSelect: (id: string) => void;
  onUploadNew: () => void;
  refreshing: boolean;
  onRefresh: () => void;
}

export function RepositorySwitcher({ repositories, selected, onSelect, onUploadNew, refreshing, onRefresh }: RepositorySwitcherProps) {
  const pop = usePopover<HTMLDivElement>();
  const list = useRef<HTMLUListElement>(null);

  useEffect(() => {
    if (pop.open) list.current?.querySelector<HTMLButtonElement>("[aria-selected='true'], button")?.focus();
  }, [pop.open]);

  const onListKey = (e: KeyboardEvent<HTMLUListElement>): void => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const items = Array.from(list.current?.querySelectorAll<HTMLButtonElement>("button") ?? []);
    const i = items.indexOf(document.activeElement as HTMLButtonElement);
    items[(i + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length]?.focus();
  };

  return (
    <div className="switcher" ref={pop.root}>
      <button type="button" className="switcher__trigger" aria-haspopup="listbox" aria-expanded={pop.open} onClick={pop.toggle}>
        <span className={`dot dot--${selected?.status ?? "unknown"}`} aria-hidden="true" />
        <span className="switcher__label">
          <span className="switcher__name">{selected ? selected.name : "No repository"}</span>
          <span className="switcher__path mono">{selected ? selected.id : "Upload one to begin"}</span>
        </span>
        <Icon name="chevronDown" size={14} />
      </button>
      {pop.open ? (
        <div className="popover switcher__pop">
          <div className="switcher__pop-head">
            <span>Uploaded repositories</span>
            <button type="button" className="switcher__refresh" onClick={onRefresh} aria-label="Refresh repository list" disabled={refreshing}>
              {refreshing ? <span className="spinner" aria-hidden="true" /> : <Icon name="refresh" size={13} />}
            </button>
          </div>
          {repositories.length === 0 ? <p className="switcher__none">No repositories uploaded yet.</p> : null}
          <ul className="switcher__list" role="listbox" aria-label="Repositories" ref={list} onKeyDown={onListKey}>
            {repositories.map((repo) => (
              <li key={repo.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={repo.id === selected?.id}
                  className="switcher__item"
                  onClick={() => {
                    onSelect(repo.id);
                    pop.close();
                  }}
                >
                  <span className={`dot dot--${repo.status}`} aria-hidden="true" />
                  <span className="switcher__item-main">
                    <span className="switcher__item-name">{repo.name}</span>
                    <span className="switcher__item-meta">
                      {repo.file_count !== null ? <span>{formatNumber(repo.file_count)} files</span> : null}
                      {repo.size_bytes !== null ? <span>{formatBytes(repo.size_bytes)}</span> : null}
                      {repo.languages.length ? <span>{repo.languages.slice(0, 3).map((l) => l.name).join(", ")}</span> : null}
                      {repo.indexed_at ? <span>{formatRelativeTime(repo.indexed_at)}</span> : null}
                    </span>
                  </span>
                  {repo.id === selected?.id ? <Icon name="check" size={14} /> : null}
                </button>
              </li>
            ))}
          </ul>
          <button
            type="button"
            className="switcher__action"
            onClick={() => {
              pop.close();
              onUploadNew();
            }}
          >
            <Icon name="upload" size={14} />
            Upload a repository
          </button>
        </div>
      ) : null}
    </div>
  );
}
