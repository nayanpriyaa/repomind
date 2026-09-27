import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, isAbortError, toApiError } from "../services/api";
import { searchRepository } from "../services/query";
import type { RetrievalMode, SearchResponse } from "../types/api";

export interface RetrievalRun {
  id: string;
  repositoryId: string;
  query: string;
  mode: RetrievalMode;
  topK: number;
  result: { status: "loading" } | { status: "done"; response: SearchResponse; durationMs: number } | { status: "error"; error: ApiError };
}

export interface RetrievalHandle {
  run: RetrievalRun | null;
  search: (params: Omit<RetrievalRun, "id" | "result">) => void;
  clear: () => void;
}

export function useRetrieval(): RetrievalHandle {
  const [run, setRun] = useState<RetrievalRun | null>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  const search = useCallback((params: Omit<RetrievalRun, "id" | "result">) => {
    controller.current?.abort();
    const c = new AbortController();
    controller.current = c;
    const id = `ret-${Date.now().toString(36)}`;
    const t0 = performance.now();
    setRun({ ...params, id, result: { status: "loading" } });
    searchRepository({ repository_id: params.repositoryId, query: params.query, mode: params.mode, top_k: params.topK }, c.signal)
      .then((response) =>
        setRun((r) => (r?.id === id ? { ...r, result: { status: "done", response, durationMs: performance.now() - t0 } } : r)),
      )
      .catch((e: unknown) => {
        if (isAbortError(e)) return;
        setRun((r) => (r?.id === id ? { ...r, result: { status: "error", error: toApiError(e, "/repositories/search") } } : r));
      });
  }, []);

  const clear = useCallback(() => {
    controller.current?.abort();
    setRun(null);
  }, []);

  return { run, search, clear };
}
