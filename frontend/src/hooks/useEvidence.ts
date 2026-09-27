import { useCallback, useEffect, useRef, useState } from "react";
import { sourceKey } from "../lib/citations";
import { ApiError, isAbortError, toApiError } from "../services/api";
import {
  excerptFromResult,
  excerptFromResults,
  fetchRetrievalForLookup,
  type ExcerptLookup,
  type ExcerptResult,
} from "../services/source";
import type { SearchResult, Source } from "../types/api";

export type ExcerptState = { status: "loading" } | ExcerptResult | { status: "error"; error: ApiError };

export interface EvidenceSelection {
  /** Groups selections so cached lookups are per investigation / retrieval run. */
  contextId: string;
  source: Source;
  /** 1-based position in the ranked source list. */
  position: number;
  total: number;
  rank: number | null;
  matchType: string | null;
  lookup: ExcerptLookup | null;
  retrieved: SearchResult | null;
}

export interface EvidenceHandle {
  selection: EvidenceSelection | null;
  excerpt: ExcerptState | null;
  select: (selection: EvidenceSelection) => void;
  clear: () => void;
  retryExcerpt: () => void;
}

export function useEvidence(): EvidenceHandle {
  const [selection, setSelection] = useState<EvidenceSelection | null>(null);
  const [excerpt, setExcerpt] = useState<ExcerptState | null>(null);
  const [attempt, setAttempt] = useState(0);
  const cache = useRef(new Map<string, Promise<SearchResult[]>>());

  useEffect(() => {
    if (!selection) {
      setExcerpt(null);
      return;
    }
    if (selection.retrieved) {
      setExcerpt(excerptFromResult(selection.retrieved));
      return;
    }
    const lookup = selection.lookup;
    if (!lookup) {
      setExcerpt({ status: "unavailable", reason: "no-content" });
      return;
    }
    let cancelled = false;
    const c = new AbortController();
    setExcerpt({ status: "loading" });
    let pending = cache.current.get(selection.contextId);
    if (!pending) {
      pending = fetchRetrievalForLookup(lookup, c.signal);
      cache.current.set(selection.contextId, pending);
    }
    pending
      .then((results) => {
        if (!cancelled) setExcerpt(excerptFromResults(selection.source, results));
      })
      .catch((e: unknown) => {
        cache.current.delete(selection.contextId);
        if (cancelled || isAbortError(e)) return;
        setExcerpt({ status: "error", error: toApiError(e, "/repositories/search") });
      });
    return () => {
      cancelled = true;
    };
  }, [selection, attempt]);

  const select = useCallback((next: EvidenceSelection) => {
    setSelection((prev) =>
      prev && prev.contextId === next.contextId && sourceKey(prev.source) === sourceKey(next.source) ? prev : next,
    );
  }, []);
  const clear = useCallback(() => setSelection(null), []);
  const retryExcerpt = useCallback(() => {
    setAttempt((a) => a + 1);
  }, []);

  return { selection, excerpt, select, clear, retryExcerpt };
}
