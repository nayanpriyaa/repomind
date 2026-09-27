import { useRef, type KeyboardEvent } from "react";
import { modeLabel } from "../../lib/format";
import { RETRIEVAL_MODES, type RetrievalMode } from "../../types/api";
import "./query.css";

const HINTS: Record<RetrievalMode, string> = {
  hybrid: "Keyword and semantic results fused with reciprocal rank fusion",
  semantic: "Vector similarity from the embedding index",
  keyword: "SQLite FTS5 full-text match on identifiers and text",
};

interface ModeSelectorProps {
  value: RetrievalMode;
  onChange: (mode: RetrievalMode) => void;
  disabled?: boolean;
}

export function ModeSelector({ value, onChange, disabled }: ModeSelectorProps) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>): void => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const i = RETRIEVAL_MODES.indexOf(value);
    const next = (i + (e.key === "ArrowRight" ? 1 : -1) + RETRIEVAL_MODES.length) % RETRIEVAL_MODES.length;
    const mode = RETRIEVAL_MODES[next];
    if (mode) {
      onChange(mode);
      refs.current[next]?.focus();
    }
  };
  return (
    <div className="segmented" role="radiogroup" aria-label="Retrieval mode" onKeyDown={onKeyDown}>
      {RETRIEVAL_MODES.map((mode, i) => (
        <button
          key={mode}
          ref={(el) => {
            refs.current[i] = el;
          }}
          type="button"
          role="radio"
          aria-checked={value === mode}
          tabIndex={value === mode ? 0 : -1}
          className={value === mode ? "is-active" : undefined}
          title={HINTS[mode]}
          disabled={disabled}
          onClick={() => onChange(mode)}
        >
          {modeLabel(mode)}
        </button>
      ))}
    </div>
  );
}
