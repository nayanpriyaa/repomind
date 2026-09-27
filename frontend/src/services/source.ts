import { matchSource } from "../lib/citations";
import type { RetrievalMode, SearchResult, Source } from "../types/api";
import { searchRepository } from "./query";

/**
 * The documented API has no file-content endpoint. Evidence text comes only from
 * `/repositories/search` results that include chunk content. When a dedicated source
 * endpoint exists, implement it here; the evidence panel consumes `ExcerptResult` only.
 */
export type ExcerptResult =
  | { status: "ready"; content: string; firstLine: number }
  | { status: "unavailable"; reason: "no-content" | "not-retrieved" };

export interface ExcerptLookup {
  repositoryId: string;
  query: string;
  mode: RetrievalMode;
  topK: number;
}

export async function fetchRetrievalForLookup(lookup: ExcerptLookup, signal?: AbortSignal): Promise<SearchResult[]> {
  const res = await searchRepository(
    { repository_id: lookup.repositoryId, query: lookup.query, mode: lookup.mode, top_k: lookup.topK },
    signal,
  );
  return res.results;
}

export function excerptFromResults(source: Source, results: readonly SearchResult[]): ExcerptResult {
  const exact = results.find(
    (r) => r.file_path === source.file_path && r.start_line === source.start_line && r.end_line === source.end_line,
  );
  const idx = exact ? results.indexOf(exact) : matchSource(results, source.file_path, source.start_line, source.end_line);
  const hit = idx === null ? undefined : results[idx];
  if (!hit) return { status: "unavailable", reason: "not-retrieved" };
  return excerptFromResult(hit);
}

export function excerptFromResult(result: SearchResult): ExcerptResult {
  return result.content
    ? { status: "ready", content: result.content, firstLine: result.start_line }
    : { status: "unavailable", reason: "no-content" };
}
