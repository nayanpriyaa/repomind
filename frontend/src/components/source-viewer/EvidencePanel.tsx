import { useState } from "react";
import type { EvidenceSelection, ExcerptState } from "../../hooks/useEvidence";
import { formatLineLabel, formatLineRange, formatScore, modeLabel, splitPath } from "../../lib/format";
import { ApiErrorNotice } from "../ui/ApiErrorNotice";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { SourceCode } from "./SourceCode";
import "./source-viewer.css";

interface EvidencePanelProps {
  selection: EvidenceSelection | null;
  excerpt: ExcerptState | null;
  onRetry: () => void;
  onStep: (delta: -1 | 1) => void;
}

export function EvidencePanel({ selection, excerpt, onRetry, onStep }: EvidencePanelProps) {
  if (!selection) {
    return (
      <section className="evidence evidence--empty" aria-label="Evidence">
        <div className="evidence__placeholder">
          <div className="evidence__glyph" aria-hidden="true">
            <span />
            <span className="is-marked" />
            <span className="is-marked" />
            <span />
          </div>
          <h2>No source selected</h2>
          <p>Select a citation or an inline reference to see the exact file and lines behind the answer.</p>
          <p className="evidence__keys">
            <kbd>[</kbd> <kbd>]</kbd> step through sources
          </p>
        </div>
      </section>
    );
  }

  const { source, position, total } = selection;
  const { dir, base } = splitPath(source.file_path);
  const location = `${source.file_path}:${formatLineRange(source.start_line, source.end_line).replace("–", "-")}`;

  return (
    <section className="evidence" aria-label="Evidence">
      <header className="evidence__bar">
        <span className="evidence__count">
          Source <strong>{position}</strong> of {total}
        </span>
        <span className="evidence__nav">
          <Button size="sm" variant="ghost" iconOnly icon="chevronLeft" aria-label="Previous source" disabled={position <= 1} onClick={() => onStep(-1)} />
          <Button size="sm" variant="ghost" iconOnly icon="chevronRight" aria-label="Next source" disabled={position >= total} onClick={() => onStep(1)} />
        </span>
      </header>

      <div className="evidence__head">
        <div className="evidence__file">
          <Icon name="file" size={15} />
          <h2 className="evidence__path mono" title={source.file_path}>
            <span className="evidence__dir">{dir}</span>
            {base}
          </h2>
          <CopyButton value={location} />
        </div>
        <p className="evidence__range mono">{formatLineLabel(source.start_line, source.end_line)}</p>

        <dl className="evidence__meta">
          <div>
            <dt>Symbol</dt>
            <dd className="mono evidence__symbol">{source.symbol ?? "—"}</dd>
          </div>
          <div>
            <dt>Chunk</dt>
            <dd className="mono">{source.chunk_type ?? "—"}</dd>
          </div>
          <div>
            <dt>Language</dt>
            <dd className="mono">{source.language ?? "—"}</dd>
          </div>
          <div>
            <dt>Score</dt>
            <dd className="mono">{formatScore(source.score)}</dd>
          </div>
          {selection.rank !== null ? (
            <div>
              <dt>Rank</dt>
              <dd className="mono">#{selection.rank}</dd>
            </div>
          ) : null}
          {selection.matchType ? (
            <div>
              <dt>Match</dt>
              <dd className="mono">{modeLabel(selection.matchType)}</dd>
            </div>
          ) : null}
        </dl>
      </div>

      <div className="evidence__code">
        <ExcerptBody selection={selection} excerpt={excerpt} onRetry={onRetry} />
      </div>
    </section>
  );
}

function ExcerptBody({ selection, excerpt, onRetry }: { selection: EvidenceSelection; excerpt: ExcerptState | null; onRetry: () => void }) {
  const { source } = selection;
  if (!excerpt || excerpt.status === "loading") {
    return (
      <div className="evidence__loading" aria-busy="true" aria-label="Loading source excerpt">
        {Array.from({ length: 9 }, (_, i) => (
          <span key={i} className="skeleton" style={{ width: `${40 + ((i * 37) % 50)}%` }} />
        ))}
      </div>
    );
  }
  if (excerpt.status === "error") {
    return (
      <div className="evidence__state">
        <ApiErrorNotice title="Unable to load the source excerpt" error={excerpt.error} onRetry={onRetry} />
      </div>
    );
  }
  if (excerpt.status === "unavailable") {
    return (
      <div className="evidence__state evidence__unavailable">
        <Icon name="code" size={18} />
        <h3>Source text unavailable</h3>
        <p>
          {excerpt.reason === "no-content"
            ? "The retrieval API returned this chunk's location but not its text, so RepoMind won't display code for it."
            : "This chunk wasn't in a fresh retrieval for the same question, so its text can't be shown here."}
        </p>
        <p>
          Open <code className="mono">{source.file_path}</code> at line {source.start_line} to verify.
        </p>
      </div>
    );
  }
  return (
    <SourceCode
      content={excerpt.content}
      firstLine={excerpt.firstLine}
      language={source.language}
      highlightStart={source.start_line}
      highlightEnd={source.end_line}
      label={`${source.file_path}, ${formatLineLabel(source.start_line, source.end_line)}`}
    />
  );
}

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  const copy = (): void => {
    void navigator.clipboard?.writeText(value).then(
      () => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1400);
      },
      () => setCopied(false),
    );
  };
  return (
    <Button size="sm" variant="ghost" iconOnly icon={copied ? "check" : "copy"} aria-label={copied ? "Copied location" : `Copy ${value}`} title={value} onClick={copy} />
  );
}
