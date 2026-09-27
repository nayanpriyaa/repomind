import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, isAbortError, toApiError } from "../services/api";
import { queryRepository } from "../services/query";
import type { QueryResponse, RetrievalMode } from "../types/api";

export type InvestigationResult =
  | { status: "loading" }
  | { status: "done"; response: QueryResponse; durationMs: number }
  | { status: "error"; error: ApiError };

export interface Investigation {
  id: string;
  repositoryId: string;
  question: string;
  mode: RetrievalMode;
  topK: number;
  submittedAt: number;
  result: InvestigationResult;
}

export interface AskParams {
  repositoryId: string;
  question: string;
  mode: RetrievalMode;
  topK: number;
}

let counter = 0;
const nextId = (): string => `inv-${Date.now().toString(36)}-${(counter += 1)}`;

export interface InvestigationsHandle {
  items: Investigation[];
  activeId: string | null;
  active: Investigation | null;
  ask: (params: AskParams) => void;
  retry: (id: string) => void;
  open: (id: string | null) => void;
}

export function useInvestigations(): InvestigationsHandle {
  const [items, setItems] = useState<Investigation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  const run = useCallback((inv: Investigation) => {
    controller.current?.abort();
    const c = new AbortController();
    controller.current = c;
    const t0 = performance.now();
    const update = (result: InvestigationResult): void =>
      setItems((list) => list.map((i) => (i.id === inv.id ? { ...i, result } : i)));

    queryRepository(
      { repository_id: inv.repositoryId, question: inv.question, mode: inv.mode, top_k: inv.topK },
      c.signal,
    )
      .then((response) => update({ status: "done", response, durationMs: performance.now() - t0 }))
      .catch((e: unknown) => {
        if (isAbortError(e)) {
          setItems((list) => list.filter((i) => i.id !== inv.id || i.result.status !== "loading"));
          return;
        }
        update({ status: "error", error: toApiError(e, "/repositories/query") });
      });
  }, []);

  const ask = useCallback(
    (params: AskParams) => {
      const inv: Investigation = { id: nextId(), ...params, submittedAt: Date.now(), result: { status: "loading" } };
      setItems((list) => [inv, ...list].slice(0, 50));
      setActiveId(inv.id);
      run(inv);
    },
    [run],
  );

  const retry = useCallback(
    (id: string) => {
      const inv = items.find((i) => i.id === id);
      if (!inv) return;
      const fresh: Investigation = { ...inv, submittedAt: Date.now(), result: { status: "loading" } };
      setItems((list) => list.map((i) => (i.id === id ? fresh : i)));
      setActiveId(id);
      run(fresh);
    },
    [items, run],
  );

  const open = useCallback((id: string | null) => setActiveId(id), []);
  const active = items.find((i) => i.id === activeId) ?? null;
  return { items, activeId, active, ask, retry, open };
}
