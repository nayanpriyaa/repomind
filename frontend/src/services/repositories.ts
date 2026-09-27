import {
  flatten,
  isRecord,
  notNull,
  pickArray,
  pickBoolean,
  pickNumber,
  pickRecord,
  pickString,
  type UnknownRecord,
} from "../lib/guards";
import type {
  LanguageCount,
  RepoIndexState,
  RepositoryStatus,
  RepositorySummary,
  UploadResult,
} from "../types/api";
import { ApiError, request } from "./api";

const NESTED = ["repository", "stats", "statistics", "summary", "result", "index", "metadata"] as const;

function classifyStatus(raw: string | null, indexedFlag: boolean | null, chunks: number | null): RepoIndexState {
  const s = raw?.toLowerCase().replace(/[\s-]+/g, "_") ?? "";
  if (["indexed", "ready", "complete", "completed", "done", "success", "succeeded", "ok"].includes(s)) return "indexed";
  if (["indexing", "running", "in_progress", "pending", "queued", "started", "processing"].includes(s)) return "indexing";
  if (["failed", "error", "errored"].includes(s)) return "failed";
  if (["not_indexed", "missing", "none", "unindexed", "not_found", "empty"].includes(s)) return "not_indexed";
  if (indexedFlag !== null) return indexedFlag ? "indexed" : "not_indexed";
  if (chunks !== null) return chunks > 0 ? "indexed" : "not_indexed";
  return "unknown";
}

function toIso(r: UnknownRecord, keys: readonly string[]): string | null {
  const s = pickString(r, keys);
  if (s) return s;
  const n = pickNumber(r, keys);
  if (n === null) return null;
  return new Date(n < 1e12 ? n * 1000 : n).toISOString();
}

function parseLanguages(value: unknown): LanguageCount[] {
  let list: LanguageCount[] = [];
  if (Array.isArray(value)) {
    list = value
      .map((item): LanguageCount | null => {
        if (typeof item === "string") return { name: item, count: null };
        if (isRecord(item)) {
          const name = pickString(item, ["language", "name"]);
          return name ? { name, count: pickNumber(item, ["count", "files", "file_count", "chunks"]) } : null;
        }
        return null;
      })
      .filter(notNull);
  } else if (isRecord(value)) {
    list = Object.entries(value).map(([name, count]) => ({
      name,
      count: typeof count === "number" ? count : null,
    }));
  }
  return list.sort((a, b) => (b.count ?? 0) - (a.count ?? 0));
}

function countOf(r: UnknownRecord, keys: readonly string[]): number | null {
  const n = pickNumber(r, keys);
  if (n !== null) return n;
  const arr = pickArray(r, keys);
  return arr ? arr.length : null;
}

export function normalizeRepository(item: unknown, fallbackId?: string): RepositorySummary | null {
  if (typeof item === "string") {
    return blankRepository(item);
  }
  if (!isRecord(item)) return null;
  const r = flatten(item, NESTED);
  const id = pickString(r, ["repository_id", "id", "slug", "name"]) ?? fallbackId ?? null;
  if (!id) return null;
  const chunk_count = countOf(r, ["chunk_count", "chunks", "total_chunks", "chunks_indexed", "num_chunks"]);
  return {
    id,
    name: pickString(r, ["name", "repository_name", "repo_name"]) ?? id,
    status: classifyStatus(pickString(r, ["status", "state", "index_status"]), pickBoolean(r, ["indexed", "is_indexed"]), chunk_count),
    file_count: countOf(r, ["file_count", "files_indexed", "indexed_files", "files", "num_files"]),
    chunk_count,
    stored_file_count: countOf(r, ["stored_file_count", "stored_files", "files_on_disk"]),
    size_bytes: pickNumber(r, ["size_bytes", "bytes", "size"]),
    languages: parseLanguages(r.languages ?? r.language_counts ?? r.language_stats),
    indexed_at: toIso(r, ["indexed_at", "last_indexed_at", "last_indexed", "completed_at", "finished_at", "updated_at"]),
  };
}

function blankRepository(id: string): RepositorySummary {
  return {
    id,
    name: id,
    status: "unknown",
    file_count: null,
    chunk_count: null,
    stored_file_count: null,
    size_bytes: null,
    languages: [],
    indexed_at: null,
  };
}

function normalizeStatus(body: unknown, id: string): RepositoryStatus {
  const base = normalizeRepository(body, id) ?? normalizeRepository(id);
  const r = isRecord(body) ? flatten(body, NESTED) : {};
  const progressRecord = pickRecord(r, ["progress"]) ?? r;
  const files_processed = pickNumber(progressRecord, ["files_processed", "processed_files", "processed"]);
  const files_total = pickNumber(progressRecord, ["files_total", "total_files", "files_discovered", "discovered_files", "total"]);
  const current_file = pickString(progressRecord, ["current_file", "current_path", "file"]);
  const summary = base ?? blankRepository(id);
  return {
    ...summary,
    progress:
      files_processed !== null || files_total !== null || current_file !== null
        ? { files_processed, files_total, current_file }
        : null,
    error: summary.status === "failed" ? pickString(r, ["error", "message", "detail"]) : null,
  };
}

export async function listRepositories(signal?: AbortSignal): Promise<RepositorySummary[]> {
  const body = await request("/repositories", { signal });
  const items = Array.isArray(body) ? body : isRecord(body) ? pickArray(body, ["repositories", "items", "data", "results"]) ?? [] : [];
  return items.map((item) => normalizeRepository(item)).filter(notNull);
}

export async function getRepositoryStatus(id: string, signal?: AbortSignal): Promise<RepositoryStatus> {
  const body = await request(`/repositories/${encodeURIComponent(id)}`, { signal });
  return normalizeStatus(body, id);
}

export async function indexRepository(id: string, force = false, signal?: AbortSignal): Promise<RepositoryStatus> {
  // The index endpoint answers with a run report, not a repository record, so the
  // authoritative counts come from a follow-up status read.
  await request("/repositories/index", { method: "POST", body: { repository_id: id, force }, signal });
  return getRepositoryStatus(id, signal);
}

/**
 * Upload a ZIP archive. The backend derives the repository ID from the filename
 * unless `name` is given, extracts the archive, and returns the stored record.
 */
export async function uploadRepository(file: File, name?: string, signal?: AbortSignal): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  const trimmed = name?.trim();
  if (trimmed) form.append("name", trimmed);

  const body = await request("/repositories/upload", { method: "POST", body: form, signal });
  const record = isRecord(body) ? (pickRecord(body, ["repository"]) ?? body) : null;
  const repository = normalizeRepository(record);
  if (!repository) {
    throw new ApiError("The upload succeeded but the response could not be read.", -1, "/repositories/upload", body);
  }
  return { repository, message: isRecord(body) ? pickString(body, ["message", "detail"]) : null };
}

export async function deleteRepository(id: string, signal?: AbortSignal): Promise<void> {
  await request(`/repositories/${encodeURIComponent(id)}`, { method: "DELETE", signal });
}
