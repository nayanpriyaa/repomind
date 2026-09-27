import type { UploadState } from "../../hooks/useUpload";
import { formatBytes, formatNumber } from "../../lib/format";
import type { RepositorySummary } from "../../types/api";
import { ApiErrorNotice } from "../ui/ApiErrorNotice";
import { Button } from "../ui/Button";
import { UploadForm } from "./UploadForm";
import "./indexing.css";

interface OnboardingProps {
  repositories: RepositorySummary[];
  upload: UploadState;
  onUpload: (file: File, name?: string) => void;
  onSelect: (id: string) => void;
  onCancel?: () => void;
}

const POINTS = [
  { title: "Structural chunks", body: "Functions, classes and methods parsed with AST and tree-sitter, not arbitrary text windows." },
  { title: "Hybrid retrieval", body: "SQLite FTS5 keyword matches and Qdrant vectors fused by reciprocal rank." },
  { title: "Grounded answers", body: "Answers are generated only from retrieved chunks, or RepoMind says the evidence isn't there." },
  { title: "File and line citations", body: "Every claim links to the exact path and line range you can open and check." },
];

export function Onboarding({ repositories, upload, onUpload, onSelect, onCancel }: OnboardingProps) {
  return (
    <div className="onboarding">
      <div className="onboarding__intro">
        <h1>Ask a codebase where things live.</h1>
        <p>Upload a repository as a .zip, index it, then ask questions. Every answer points at real files and line numbers.</p>
      </div>

      <UploadForm onUpload={onUpload} busy={upload.phase === "uploading"} autoFocus />

      {upload.phase === "failed" ? (
        <ApiErrorNotice
          title={`Could not upload ${upload.fileName}`}
          error={upload.error}
          hints={[
            "the file is a valid .zip archive",
            "a repository with that name doesn't already exist",
            "the archive is under the server's size limit",
          ]}
        />
      ) : null}

      {repositories.length > 0 ? (
        <section className="onboarding__existing" aria-label="Existing repositories">
          <h2>Or open an uploaded repository</h2>
          <ul>
            {repositories.map((r) => (
              <li key={r.id}>
                <button type="button" onClick={() => onSelect(r.id)}>
                  <span className={`dot dot--${r.status}`} aria-hidden="true" />
                  <span className="onboarding__repo-name">{r.name}</span>
                  <span className="onboarding__repo-meta">
                    {r.status === "indexed"
                      ? `${formatNumber(r.chunk_count)} chunks`
                      : r.stored_file_count !== null
                        ? `${formatNumber(r.stored_file_count)} files, not indexed`
                        : "not indexed"}
                    {r.size_bytes !== null ? ` · ${formatBytes(r.size_bytes)}` : ""}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <dl className="onboarding__points">
        {POINTS.map((p) => (
          <div key={p.title}>
            <dt>{p.title}</dt>
            <dd>{p.body}</dd>
          </div>
        ))}
      </dl>

      {onCancel ? (
        <div>
          <Button variant="ghost" size="sm" icon="chevronLeft" onClick={onCancel}>
            Back to workspace
          </Button>
        </div>
      ) : null}
    </div>
  );
}
