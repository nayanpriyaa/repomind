export type UnknownRecord = Record<string, unknown>;

export function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function notNull<T>(value: T | null | undefined): value is T {
  return value !== null && value !== undefined;
}

export function pickString(r: UnknownRecord, keys: readonly string[]): string | null {
  for (const key of keys) {
    const v = r[key];
    if (typeof v === "string" && v.trim() !== "") return v;
  }
  return null;
}

export function pickNumber(r: UnknownRecord, keys: readonly string[]): number | null {
  for (const key of keys) {
    const v = r[key];
    if (typeof v === "number" && Number.isFinite(v)) return v;
    if (typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v))) return Number(v);
  }
  return null;
}

export function pickBoolean(r: UnknownRecord, keys: readonly string[]): boolean | null {
  for (const key of keys) {
    const v = r[key];
    if (typeof v === "boolean") return v;
  }
  return null;
}

export function pickRecord(r: UnknownRecord, keys: readonly string[]): UnknownRecord | null {
  for (const key of keys) {
    const v = r[key];
    if (isRecord(v)) return v;
  }
  return null;
}

export function pickArray(r: UnknownRecord, keys: readonly string[]): unknown[] | null {
  for (const key of keys) {
    const v = r[key];
    if (Array.isArray(v)) return v;
  }
  return null;
}

/** Shallow-merge nested objects under `nestedKeys` into the parent. Top-level keys win. */
export function flatten(r: UnknownRecord, nestedKeys: readonly string[]): UnknownRecord {
  let out: UnknownRecord = { ...r };
  for (const key of nestedKeys) {
    const nested = r[key];
    if (isRecord(nested)) out = { ...nested, ...out };
  }
  return out;
}


export function normalizePath(path: string): string {
  return path.replace(/\\/g, "/").replace(/^\.\//, "").replace(/^\/+/, "");
}
