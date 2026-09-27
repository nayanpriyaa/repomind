export type RetrievalMode = "hybrid" | "semantic" | "keyword";

export const RETRIEVAL_MODES: readonly RetrievalMode[] = ["hybrid", "semantic", "keyword"];

export interface QueryRequest {
  /** Server-side slug. The API never accepts or returns filesystem paths. */
  repository_id: string;
  question: string;
  top_k: number;
  mode: RetrievalMode;
}

export interface SearchRequest {
  repository_id: string;
  query: string;
  top_k: number;
  mode: RetrievalMode;
}

export interface Source {
  file_path: string;
  start_line: number;
  end_line: number;
  symbol: string | null;
  language: string | null;
  chunk_type: string | null;
  score: number | null;
}

export interface QueryResponse {
  question: string;
  answer: string;
  mode: RetrievalMode;
  grounded: boolean;
  chunks_used: number;
  context_characters: number | null;
  sources: Source[];
}

export interface BackendRanks {
  semantic: number | null;
  keyword: number | null;
}

export interface SearchResult extends Source {
  rank: number;
  match_type: string | null;
  /** Chunk text, only if the backend returns it. Never synthesized. */
  content: string | null;
  backend_ranks: BackendRanks;
}

export interface SearchResponse {
  query: string;
  mode: RetrievalMode;
  results: SearchResult[];
}

export type RepoIndexState = "indexed" | "indexing" | "failed" | "not_indexed" | "unknown";

export interface LanguageCount {
  name: string;
  count: number | null;
}

export interface RepositorySummary {
  /** Slug assigned by the backend when the archive was uploaded. */
  id: string;
  name: string;
  status: RepoIndexState;
  /** Files the indexer ingested. Null until the repository has been indexed. */
  file_count: number | null;
  chunk_count: number | null;
  /** Files present on disk, known as soon as the upload lands. */
  stored_file_count: number | null;
  size_bytes: number | null;
  languages: LanguageCount[];
  indexed_at: string | null;
}

export interface UploadResult {
  repository: RepositorySummary;
  message: string | null;
}

export interface IndexProgress {
  files_processed: number | null;
  files_total: number | null;
  current_file: string | null;
}

export interface RepositoryStatus extends RepositorySummary {
  progress: IndexProgress | null;
  error: string | null;
}

export type CheckState = "ready" | "degraded" | "unavailable";

export interface ServiceCheck {
  name: string;
  state: CheckState;
  detail: string | null;
}

export interface HealthReport {
  live: boolean;
  ready: boolean;
  readyReachable: boolean;
  checks: ServiceCheck[];
  checkedAt: number;
}

export type HealthState = "loading" | "ready" | "degraded" | "unavailable";
