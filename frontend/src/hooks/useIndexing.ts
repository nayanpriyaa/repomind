import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, isAbortError, toApiError } from "../services/api";
import { getRepositoryStatus, indexRepository } from "../services/repositories";
import type { RepositoryStatus } from "../types/api";

export type IndexingState =
  | { phase: "idle" }
  | { phase: "running"; repositoryId: string; startedAt: number; latest: RepositoryStatus | null }
  | { phase: "succeeded"; repositoryId: string; startedAt: number; finishedAt: number; result: RepositoryStatus }
  | { phase: "failed"; repositoryId: string; startedAt: number; finishedAt: number; error: ApiError; latest: RepositoryStatus | null };

const POLL_MS = 1500;
const sleep = (ms: number, signal: AbortSignal): Promise<void> =>
  new Promise((resolve, reject) => {
    const id = window.setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      window.clearTimeout(id);
      reject(new DOMException("Aborted", "AbortError"));
    });
  });

export interface IndexingHandle {
  state: IndexingState;
  start: (repositoryId: string, force?: boolean) => void;
  dismiss: () => void;
}

export function useIndexing(onComplete: (repositoryId: string) => void): IndexingHandle {
  const [state, setState] = useState<IndexingState>({ phase: "idle" });
  const controller = useRef<AbortController | null>(null);
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  useEffect(() => () => controller.current?.abort(), []);

  const start = useCallback((repositoryId: string, force = false) => {
    controller.current?.abort();
    const c = new AbortController();
    controller.current = c;
    const startedAt = Date.now();
    let latest: RepositoryStatus | null = null;
    setState({ phase: "running", repositoryId, startedAt, latest: null });

    const setLatest = (s: RepositoryStatus): void => {
      latest = s;
      setState((prev) => (prev.phase === "running" && prev.startedAt === startedAt ? { ...prev, latest: s } : prev));
    };

    // Opportunistic status polling while the (possibly synchronous) index request is open.
    let requestOpen = true;
    const poll = async (): Promise<void> => {
      while (requestOpen && !c.signal.aborted) {
        await sleep(POLL_MS, c.signal);
        if (!requestOpen) return;
        try {
          setLatest(await getRepositoryStatus(repositoryId, c.signal));
        } catch (e) {
          if (isAbortError(e)) return;
        }
      }
    };
    void poll().catch(() => undefined);

    const run = async (): Promise<void> => {
      try {
        let result = await indexRepository(repositoryId, force, c.signal);
        requestOpen = false;
        setLatest(result);
        // Asynchronous backends acknowledge immediately; follow status until terminal.
        while (result.status === "indexing") {
          await sleep(POLL_MS, c.signal);
          result = await getRepositoryStatus(repositoryId, c.signal);
          setLatest(result);
        }
        if (result.status === "failed") {
          throw new ApiError(result.error ?? "Indexing reported a failure.", -1, "/repositories/index", null);
        }
        setState({ phase: "succeeded", repositoryId, startedAt, finishedAt: Date.now(), result });
        onCompleteRef.current(repositoryId);
      } catch (e) {
        requestOpen = false;
        if (isAbortError(e)) return;
        setState({ phase: "failed", repositoryId, startedAt, finishedAt: Date.now(), error: toApiError(e, "/repositories/index"), latest });
      }
    };
    void run();
  }, []);

  const dismiss = useCallback(() => {
    controller.current?.abort();
    setState({ phase: "idle" });
  }, []);

  return { state, start, dismiss };
}
