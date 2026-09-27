import { flatten, isRecord, notNull, pickArray, pickBoolean, pickNumber, pickRecord, pickString } from "../lib/guards";
import {
  RETRIEVAL_MODES,
  type QueryRequest,
  type QueryResponse,
  type RetrievalMode,
  type SearchRequest,
  type SearchResponse,
  type SearchResult,
  type Source,
} from "../types/api";
import { ApiError, request } from "./api";

function toMode(value: string | null, fallback: RetrievalMode): RetrievalMode {
  const v = value?.toLowerCase();
  return RETRIEVAL_MODES.find((m) => m === v) ?? fallback;
}

export function normalizeSource(item: unknown): Source | null {
  if (!isRecord(item)) return null;
  const r = flatten(item, ["metadata", "payload", "chunk"]);
  const file_path = pickString(r, ["file_path", "path", "file", "relative_path"]);
  const start_line = pickNumber(r, ["start_line", "line_start", "start"]);
  if (!file_path || start_line === null) return null;
  return {
    file_path,
    start_line,
    end_line: pickNumber(r, ["end_line", "line_end", "end"]) ?? start_line,
    symbol: pickString(r, ["symbol", "symbol_name", "qualified_name", "name"]),
    language: pickString(r, ["language", "lang"]),
    chunk_type: pickString(r, ["chunk_type", "kind", "node_type", "type"]),
    score: pickNumber(r, ["score", "rrf_score", "similarity", "relevance"]),
  };
}

function normalizeSearchResult(item: unknown, index: number): SearchResult | null {
  const source = normalizeSource(item);
  if (!source || !isRecord(item)) return null;
  const r = flatten(item, ["metadata", "payload", "chunk"]);
  const ranks = pickRecord(r, ["ranks", "backend_ranks", "component_ranks"]) ?? r;
  return {
    ...source,
    rank: pickNumber(r, ["rank", "position"]) ?? index + 1,
    match_type: pickString(r, ["match_type", "retrieval", "retriever", "method", "match"]),
    content: pickString(r, ["content", "text", "code", "snippet", "excerpt"]),
    backend_ranks: {
      semantic: pickNumber(ranks, ["semantic_rank", "semantic", "vector_rank", "dense_rank", "qdrant_rank"]),
      keyword: pickNumber(ranks, ["keyword_rank", "keyword", "fts_rank", "lexical_rank", "bm25_rank", "sqlite_rank"]),
    },
  };
}

export async function queryRepository(req: QueryRequest, signal?: AbortSignal): Promise<QueryResponse> {
  const body = await request("/repositories/query", { method: "POST", body: req, signal });
  if (!isRecord(body)) throw new ApiError("The query endpoint returned an unexpected response.", -1, "/repositories/query", body);
  const sources = (pickArray(body, ["sources"]) ?? []).map(normalizeSource).filter(notNull);
  return {
    question: pickString(body, ["question"]) ?? req.question,
    answer: pickString(body, ["answer"]) ?? "",
    mode: toMode(pickString(body, ["mode"]), req.mode),
    // Missing flag is treated as ungrounded: never manufacture confidence.
    grounded: pickBoolean(body, ["grounded"]) ?? false,
    chunks_used: pickNumber(body, ["chunks_used"]) ?? sources.length,
    context_characters: pickNumber(body, ["context_characters"]),
    sources,
  };
}

export async function searchRepository(req: SearchRequest, signal?: AbortSignal): Promise<SearchResponse> {
  const body = await request("/repositories/search", { method: "POST", body: req, signal });
  const items = Array.isArray(body) ? body : isRecord(body) ? pickArray(body, ["results", "chunks", "hits", "matches", "sources"]) ?? [] : [];
  return {
    query: (isRecord(body) && pickString(body, ["query", "question"])) || req.query,
    mode: toMode(isRecord(body) ? pickString(body, ["mode"]) : null, req.mode),
    results: items.map(normalizeSearchResult).filter(notNull),
  };
}
