import { isRecord } from "../lib/guards";

const RAW_BASE = import.meta.env.VITE_API_BASE_URL;

export const API_BASE_URL = (typeof RAW_BASE === "string" && RAW_BASE.trim() !== "" ? RAW_BASE : "/api").replace(
  /\/+$/,
  "",
);

export class ApiError extends Error {
  readonly status: number;
  readonly path: string;
  readonly body: unknown;

  constructor(message: string, status: number, path: string, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.path = path;
    this.body = body;
  }

  get isNetworkError(): boolean {
    return this.status === 0;
  }
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export function toApiError(error: unknown, path: string): ApiError {
  if (error instanceof ApiError) return error;
  const message = error instanceof Error ? error.message : "Unexpected client error";
  return new ApiError(message, -1, path, null);
}

function detailFromBody(body: unknown): string | null {
  if (typeof body === "string") return body.trim().slice(0, 500) || null;
  if (!isRecord(body)) return null;
  const detail = body.detail ?? body.message ?? body.error;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((entry) => {
        if (!isRecord(entry) || typeof entry.msg !== "string") return null;
        const loc = Array.isArray(entry.loc) ? entry.loc.filter((p) => p !== "body").join(".") : "";
        return loc ? `${loc}: ${entry.msg}` : entry.msg;
      })
      .filter((m): m is string => m !== null);
    return messages.length ? messages.join("; ") : null;
  }
  return null;
}

export interface RequestOptions {
  method?: "GET" | "POST" | "DELETE";
  /** Plain values are sent as JSON; a FormData body is sent as multipart. */
  body?: unknown;
  query?: Record<string, string | number | undefined>;
  signal?: AbortSignal;
}

function bodyInit(body: unknown): { body: BodyInit | undefined; headers: Record<string, string> } {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body === undefined) return { body: undefined, headers };
  // The browser must set Content-Type itself for multipart, so it can append
  // the boundary. Setting it by hand produces an unparseable request.
  if (body instanceof FormData) return { body, headers };
  return { body: JSON.stringify(body), headers: { ...headers, "Content-Type": "application/json" } };
}

/** Single transport for every backend call. Returns parsed JSON as `unknown`; callers normalize. */
export async function request(path: string, options: RequestOptions = {}): Promise<unknown> {
  const { method = "GET", body, query, signal } = options;
  const url = new URL(API_BASE_URL + path, window.location.origin);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined) url.searchParams.set(key, String(value));
  }

  const init = bodyInit(body);
  let response: Response;
  try {
    response = await fetch(url, { method, signal, headers: init.headers, body: init.body });
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new ApiError(`Could not reach the RepoMind API at ${API_BASE_URL}`, 0, path, null);
  }

  const text = await response.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }

  if (!response.ok) {
    // Reverse proxies reject oversized uploads before FastAPI sees them, so 413
    // arrives with an HTML body and no usable detail.
    const fallback =
      response.status === 413
        ? "That archive is larger than the server accepts."
        : `${response.status} ${response.statusText}`.trim();
    throw new ApiError(detailFromBody(parsed) ?? fallback, response.status, path, parsed);
  }
  return parsed;
}
