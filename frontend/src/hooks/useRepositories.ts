import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, isAbortError, toApiError } from "../services/api";
import { getRepositoryStatus, listRepositories } from "../services/repositories";
import type { RepositoryStatus, RepositorySummary } from "../types/api";

const STORAGE_KEY = "repomind.selectedRepository";

function readStored(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStored(id: string | null): void {
  try {
    if (id) window.localStorage.setItem(STORAGE_KEY, id);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage unavailable: selection simply isn't remembered */
  }
}

export interface RepositoriesHandle {
  repositories: RepositorySummary[];
  loadState: "loading" | "ready" | "error";
  refreshing: boolean;
  error: ApiError | null;
  selectedId: string | null;
  selected: RepositorySummary | null;
  select: (id: string | null) => void;
  reload: () => Promise<RepositorySummary[]>;
}

export function useRepositories(): RepositoriesHandle {
  const [repositories, setRepositories] = useState<RepositorySummary[]>([]);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [selectedId, setSelectedPath] = useState<string | null>(readStored);
  const controller = useRef<AbortController | null>(null);

  const select = useCallback((path: string | null) => {
    setSelectedPath(path);
    writeStored(path);
  }, []);

  const reload = useCallback(async (): Promise<RepositorySummary[]> => {
    controller.current?.abort();
    const c = new AbortController();
    controller.current = c;
    setRefreshing(true);
    try {
      const list = await listRepositories(c.signal);
      setRepositories(list);
      setError(null);
      setLoadState("ready");
      setSelectedPath((current) => {
        if (current && list.some((r) => r.id === current)) return current;
        const next = list.find((r) => r.status === "indexed")?.id ?? list[0]?.id ?? null;
        writeStored(next);
        return next;
      });
      return list;
    } catch (e) {
      if (isAbortError(e)) return [];
      setError(toApiError(e, "/repositories"));
      setLoadState((s) => (s === "ready" ? "ready" : "error"));
      return [];
    } finally {
      if (!c.signal.aborted) setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void reload();
    return () => controller.current?.abort();
  }, [reload]);

  const selected = repositories.find((r) => r.id === selectedId) ?? null;
  return { repositories, loadState, refreshing, error, selectedId, selected, select, reload };
}

export interface RepositoryStatusHandle {
  status: RepositoryStatus | null;
  loading: boolean;
  error: ApiError | null;
  refresh: () => void;
}

export function useRepositoryStatus(id: string | null, revision: number): RepositoryStatusHandle {
  const [status, setStatus] = useState<RepositoryStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    setStatus(null);
    setError(null);
    if (!id) return;
    const c = new AbortController();
    setLoading(true);
    getRepositoryStatus(id, c.signal)
      .then((s) => setStatus(s))
      .catch((e: unknown) => {
        if (!isAbortError(e)) setError(toApiError(e, `/repositories/${id}`));
      })
      .finally(() => {
        if (!c.signal.aborted) setLoading(false);
      });
    return () => c.abort();
  }, [id, revision, tick]);

  const refresh = useCallback(() => setTick((t) => t + 1), []);
  return { status, loading, error, refresh };
}
