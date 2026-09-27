import { formatLineRange, formatScore, splitPath } from "../../lib/format";
import type { Source } from "../../types/api";
import "./citations.css";

interface CitationProps {
  source: Source;
  position: number;
  selected: boolean;
  onSelect: () => void;
  /** Number of inline answer references pointing at this source. */
  referenced?: number;
}

export function Citation({ source, position, selected, onSelect, referenced = 0 }: CitationProps) {
  const { dir, base } = splitPath(source.file_path);
  return (
    <button
      type="button"
      className={`citation${selected ? " is-selected" : ""}`}
      aria-pressed={selected}
      aria-label={`Source ${position}: ${source.file_path}, lines ${formatLineRange(source.start_line, source.end_line)}${source.symbol ? `, ${source.symbol}` : ""}`}
      onClick={onSelect}
    >
      <span className="citation__pos mono" aria-hidden="true">{position}</span>
      <span className="citation__main">
        <span className="citation__path mono" title={source.file_path}>
          <span className="citation__dir">{dir}</span>
          <span className="citation__base">{base}</span>
        </span>
        <span className="citation__meta">
          {source.symbol ? <span className="citation__symbol mono">{source.symbol}</span> : <span className="citation__nosymbol">no symbol</span>}
          {source.chunk_type ? <span className="citation__tag">{source.chunk_type}</span> : null}
          {source.language ? <span className="citation__tag">{source.language}</span> : null}
          {referenced > 0 ? <span className="citation__cited">cited {referenced > 1 ? `${referenced}×` : ""} in answer</span> : null}
        </span>
      </span>
      <span className="citation__side">
        <span className="citation__lines mono">L{formatLineRange(source.start_line, source.end_line)}</span>
        <span className="citation__score mono" title="Retrieval score">{formatScore(source.score)}</span>
      </span>
    </button>
  );
}

interface InlineRefProps {
  text: string;
  matched: boolean;
  selected: boolean;
  onSelect?: () => void;
}

export function InlineRef({ text, matched, selected, onSelect }: InlineRefProps) {
  if (!matched || !onSelect) {
    return (
      <span className="inline-ref is-unmatched mono" title="Not among the retrieved sources for this answer">
        {text}
      </span>
    );
  }
  return (
    <button
      type="button"
      className={`inline-ref mono${selected ? " is-selected" : ""}`}
      aria-pressed={selected}
      aria-label={`Show evidence for ${text}`}
      onClick={onSelect}
    >
      {text}
    </button>
  );
}
