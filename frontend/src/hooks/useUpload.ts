import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, isAbortError, toApiError } from "../services/api";
import { uploadRepository } from "../services/repositories";
import type { RepositorySummary } from "../types/api";

export type UploadState =
  | { phase: "idle" }
  | { phase: "uploading"; fileName: string; startedAt: number }
  | { phase: "succeeded"; repository: RepositorySummary; message: string | null }
  | { phase: "failed"; fileName: string; error: ApiError };

export interface UploadHandle {
  state: UploadState;
  upload: (file: File, name?: string) => void;
  reset: () => void;
}

const MAX_BYTES = 200 * 1024 * 1024;

/** Client-side guard so an obviously wrong file never costs an upload round trip. */
function precheck(file: File): string | null {
  if (!/\.zip$/i.test(file.name)) return "Only .zip archives can be uploaded.";
  if (file.size === 0) return "That file is empty.";
  if (file.size > MAX_BYTES) return `That archive is ${Math.round(file.size / (1024 * 1024))} MB; the limit is 200 MB.`;
  return null;
}

export function useUpload(onUploaded: (repository: RepositorySummary) => void): UploadHandle {
  const [state, setState] = useState<UploadState>({ phase: "idle" });
  const controller = useRef<AbortController | null>(null);
  const onUploadedRef = useRef(onUploaded);
  onUploadedRef.current = onUploaded;

  useEffect(() => () => controller.current?.abort(), []);

  const upload = useCallback((file: File, name?: string) => {
    const problem = precheck(file);
    if (problem) {
      setState({ phase: "failed", fileName: file.name, error: new ApiError(problem, -1, "/repositories/upload", null) });
      return;
    }

    controller.current?.abort();
    const c = new AbortController();
    controller.current = c;
    setState({ phase: "uploading", fileName: file.name, startedAt: Date.now() });

    void uploadRepository(file, name, c.signal)
      .then((result) => {
        if (c.signal.aborted) return;
        setState({ phase: "succeeded", repository: result.repository, message: result.message });
        onUploadedRef.current(result.repository);
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return;
        setState({ phase: "failed", fileName: file.name, error: toApiError(error, "/repositories/upload") });
      });
  }, []);

  const reset = useCallback(() => {
    controller.current?.abort();
    setState({ phase: "idle" });
  }, []);

  return { state, upload, reset };
}
