import type { ApiError } from "../../services/api";
import { API_BASE_URL } from "../../services/api";
import { Button } from "./Button";
import { Notice } from "./Notice";

interface ApiErrorNoticeProps {
  title: string;
  error: ApiError;
  hints?: string[];
  onRetry?: () => void;
}

function defaultHints(error: ApiError): string[] {
  if (error.isNetworkError) {
    return [
      "the backend is running on port 8000",
      API_BASE_URL.startsWith("/") ? "the Vite dev server proxy for /api is active" : `VITE_API_BASE_URL (${API_BASE_URL}) is correct`,
    ];
  }
  if (error.status === 404) return ["the repository still exists on the server", "the backend version exposes this endpoint"];
  if (error.status === 403) return ["the repository path is on the server's allowlist"];
  if (error.status === 422) return ["the request matches the backend's schema"];
  if (error.status >= 500) return ["required services (SQLite, Qdrant, LLM) are available", "the backend logs for this request"];
  return [];
}

export function ApiErrorNotice({ title, error, hints, onRetry }: ApiErrorNoticeProps) {
  const list = hints ?? defaultHints(error);
  const status = error.status > 0 ? `HTTP ${error.status} · ` : "";
  return (
    <Notice
      tone="error"
      title={title}
      actions={onRetry ? <Button size="sm" icon="refresh" onClick={onRetry}>Retry</Button> : undefined}
    >
      <p>{error.message}</p>
      {list.length > 0 ? (
        <>
          <p>Check that:</p>
          <ul>
            {list.map((h) => (
              <li key={h}>{h}</li>
            ))}
          </ul>
        </>
      ) : null}
      <p className="notice__detail">
        {status}
        {error.path}
      </p>
    </Notice>
  );
}
