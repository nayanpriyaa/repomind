import { useId, useRef, useState, type DragEvent } from "react";
import { formatBytes } from "../../lib/format";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import "./indexing.css";

interface UploadFormProps {
  onUpload: (file: File, name?: string) => void;
  busy: boolean;
  autoFocus?: boolean;
}

/**
 * Replaces the old server-path field. Repositories arrive as ZIP archives; the
 * backend assigns the identifier, so nothing here knows a filesystem path.
 */
export function UploadForm({ onUpload, busy, autoFocus }: UploadFormProps) {
  const inputId = useId();
  const nameId = useId();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [dragging, setDragging] = useState(false);

  const accept = (dropped: File | undefined): void => {
    if (dropped) setFile(dropped);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>): void => {
    event.preventDefault();
    setDragging(false);
    if (!busy) accept(event.dataTransfer.files?.[0]);
  };

  return (
    <form
      className="upload-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (file && !busy) onUpload(file, name);
      }}
    >
      <div
        className={`upload-drop${dragging ? " is-dragging" : ""}${file ? " has-file" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <input
          ref={input}
          id={inputId}
          type="file"
          accept=".zip,application/zip,application/x-zip-compressed"
          className="upload-drop__input"
          disabled={busy}
          autoFocus={autoFocus}
          onChange={(event) => {
            accept(event.target.files?.[0]);
            event.target.value = "";
          }}
        />
        <Icon name={file ? "checkCircle" : "folder"} size={20} />
        {file ? (
          <p className="upload-drop__file">
            <span className="mono">{file.name}</span>
            <span className="upload-drop__size">{formatBytes(file.size)}</span>
          </p>
        ) : (
          <p className="upload-drop__prompt">
            <label htmlFor={inputId}>Choose a .zip</label> or drop one here
          </p>
        )}
        {file ? (
          <button type="button" className="upload-drop__change" onClick={() => input.current?.click()} disabled={busy}>
            Choose a different file
          </button>
        ) : null}
      </div>

      <div className="upload-form__row">
        <div className="upload-form__name">
          <label htmlFor={nameId}>Name (optional)</label>
          <input
            id={nameId}
            className="upload-form__input mono"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={file ? file.name.replace(/\.zip$/i, "") : "taken from the filename"}
            spellCheck={false}
            autoComplete="off"
            disabled={busy}
          />
        </div>
        <Button type="submit" variant="primary" icon="upload" loading={busy} disabled={!file || busy}>
          Upload repository
        </Button>
      </div>

      <p className="upload-form__hint">
        The archive is extracted on the server, never executed. Secret files such as <span className="mono">.env</span> and
        private keys are excluded from indexing.
      </p>
    </form>
  );
}
