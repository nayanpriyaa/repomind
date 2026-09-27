import { isRecord, pickString, type UnknownRecord } from "../lib/guards";
import type { CheckState, HealthReport, HealthState, ServiceCheck } from "../types/api";
import { ApiError, request } from "./api";

const READY_WORDS = new Set(["ok", "ready", "healthy", "up", "pass", "passing", "available", "connected", "true"]);
const DOWN_WORDS = new Set(["error", "down", "fail", "failed", "unavailable", "unreachable", "false", "missing", "not_ready"]);
const META_KEYS = new Set(["status", "ready", "message", "detail", "version", "timestamp", "time", "uptime", "service", "name"]);
const CONTAINER_KEYS = ["checks", "components", "services", "dependencies", "details"] as const;

function classify(word: string): CheckState {
  const w = word.trim().toLowerCase();
  if (READY_WORDS.has(w)) return "ready";
  if (DOWN_WORDS.has(w)) return "unavailable";
  return "degraded";
}

function bodyReportsOk(body: unknown): boolean {
  if (!isRecord(body)) return true;
  if (typeof body.ready === "boolean") return body.ready;
  if (typeof body.status === "string") return classify(body.status) === "ready";
  return true;
}

function checkFrom(name: string, value: unknown): ServiceCheck | null {
  if (typeof value === "boolean") return { name, state: value ? "ready" : "unavailable", detail: null };
  if (typeof value === "string") {
    const state = classify(value);
    return { name, state, detail: state === "ready" ? null : value };
  }
  if (isRecord(value)) {
    const flag = typeof value.ok === "boolean" ? value.ok : typeof value.ready === "boolean" ? value.ready : null;
    const status = pickString(value, ["status", "state"]);
    const state: CheckState = flag !== null ? (flag ? "ready" : "unavailable") : status ? classify(status) : "degraded";
    return { name, state, detail: pickString(value, ["detail", "message", "error", "reason"]) };
  }
  return null;
}

function parseChecks(body: unknown): ServiceCheck[] {
  if (!isRecord(body)) return [];
  for (const key of CONTAINER_KEYS) {
    const container = body[key];
    if (Array.isArray(container)) {
      return container
        .map((item) => (isRecord(item) ? checkFrom(pickString(item, ["name", "service", "component"]) ?? "service", item) : null))
        .filter((c): c is ServiceCheck => c !== null);
    }
    if (isRecord(container)) return entriesToChecks(container);
  }
  return entriesToChecks(Object.fromEntries(Object.entries(body).filter(([k]) => !META_KEYS.has(k))));
}

function entriesToChecks(r: UnknownRecord): ServiceCheck[] {
  return Object.entries(r)
    .map(([name, value]) => checkFrom(name, value))
    .filter((c): c is ServiceCheck => c !== null);
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthReport> {
  const [health, ready] = await Promise.allSettled([request("/health", { signal }), request("/ready", { signal })]);

  const live = health.status === "fulfilled" && bodyReportsOk(health.value);
  let readyBody: unknown = null;
  let readyOk = false;
  let readyReachable = false;

  if (ready.status === "fulfilled") {
    readyBody = ready.value;
    readyOk = bodyReportsOk(ready.value);
    readyReachable = true;
  } else if (ready.reason instanceof ApiError && ready.reason.status > 0) {
    // FastAPI readiness probes typically answer 503 with a body describing failing checks.
    readyBody = ready.reason.body;
    readyReachable = true;
  }

  const checks = parseChecks(readyBody);
  return {
    live,
    ready: readyOk && checks.every((c) => c.state === "ready"),
    readyReachable,
    checks,
    checkedAt: Date.now(),
  };
}

export function deriveHealthState(report: HealthReport | null): HealthState {
  if (!report) return "loading";
  if (!report.live && !report.readyReachable) return "unavailable";
  if (!report.live || !report.ready) return "degraded";
  return "ready";
}
