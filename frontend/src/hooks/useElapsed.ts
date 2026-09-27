import { useEffect, useState } from "react";

/** Milliseconds since `since`, ticking while `active`. */
export function useElapsed(since: number | null, active: boolean, stepMs = 250): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), stepMs);
    return () => window.clearInterval(id);
  }, [active, stepMs]);
  return since === null ? 0 : Math.max(0, now - since);
}
