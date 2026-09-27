import { useCallback, useEffect, useRef, useState } from "react";
import { deriveHealthState, fetchHealth } from "../services/health";
import type { HealthReport, HealthState } from "../types/api";

export interface HealthHandle {
  report: HealthReport | null;
  state: HealthState;
  checking: boolean;
  check: () => void;
}

export function useHealth(intervalMs = 30_000): HealthHandle {
  const [report, setReport] = useState<HealthReport | null>(null);
  const [checking, setChecking] = useState(false);
  const controller = useRef<AbortController | null>(null);

  const check = useCallback(() => {
    controller.current?.abort();
    const c = new AbortController();
    controller.current = c;
    setChecking(true);
    void fetchHealth(c.signal).then((r) => {
      if (c.signal.aborted) return;
      setReport(r);
      setChecking(false);
    });
  }, []);

  useEffect(() => {
    check();
    const id = window.setInterval(check, intervalMs);
    return () => {
      window.clearInterval(id);
      controller.current?.abort();
    };
  }, [check, intervalMs]);

  return { report, state: deriveHealthState(report), checking, check };
}
