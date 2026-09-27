import { forwardRef, useId, type KeyboardEvent } from "react";
import type { RetrievalMode } from "../../types/api";
import { Button } from "../ui/Button";
import { ModeSelector } from "./ModeSelector";
import "./query.css";

interface ComposerProps {
  repositoryName: string;
  value: string;
  onChange: (value: string) => void;
  mode: RetrievalMode;
  onModeChange: (mode: RetrievalMode) => void;
  topK: number;
  onTopKChange: (value: number) => void;
  onSubmit: () => void;
  busy: boolean;
  disabled?: boolean;
  disabledReason?: string;
  submitLabel: string;
  placeholder: string;
}

const IS_MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

export const Composer = forwardRef<HTMLTextAreaElement, ComposerProps>(function Composer(
  { repositoryName, value, onChange, mode, onModeChange, topK, onTopKChange, onSubmit, busy, disabled, disabledReason, submitLabel, placeholder },
  ref,
) {
  const id = useId();
  const canSubmit = value.trim().length > 0 && !busy && !disabled;

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      if (canSubmit) onSubmit();
    }
    if (e.key === "Escape" && value) {
      e.preventDefault();
      onChange("");
    }
  };

  return (
    <form
      className={`composer${disabled ? " is-disabled" : ""}`}
      onSubmit={(e) => {
        e.preventDefault();
        if (canSubmit) onSubmit();
      }}
    >
      <label htmlFor={`${id}-q`} className="sr-only">
        Question for {repositoryName}
      </label>
      <textarea
        ref={ref}
        id={`${id}-q`}
        className="composer__input"
        value={value}
        rows={2}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        spellCheck={false}
      />
      <div className="composer__bar">
        <ModeSelector value={mode} onChange={onModeChange} disabled={disabled} />
        <label className="composer__topk" title="Number of chunks to retrieve">
          <span>Top</span>
          <select value={topK} onChange={(e) => onTopKChange(Number(e.target.value))} disabled={disabled} aria-label="Top K chunks">
            {[3, 5, 8, 10, 15, 20].map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </label>
        <span className="composer__spacer" />
        {disabledReason ? <span className="composer__reason">{disabledReason}</span> : null}
        {value ? (
          <Button size="sm" variant="ghost" onClick={() => onChange("")} disabled={busy}>
            Clear
          </Button>
        ) : null}
        <span className="composer__hint" aria-hidden="true">
          <kbd>{IS_MAC ? "⌘" : "Ctrl"}</kbd>
          <kbd>↵</kbd>
        </span>
        <Button type="submit" variant="primary" size="sm" loading={busy} disabled={!canSubmit}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
});
