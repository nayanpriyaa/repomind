import type { HealthHandle } from "../../hooks/useHealth";
import { API_BASE_URL } from "../../services/api";
import type { HealthState } from "../../types/api";
import { Button } from "../ui/Button";
import { usePopover } from "../ui/usePopover";
import "./health.css";

const LABEL: Record<HealthState, string> = {
  loading: "Checking",
  ready: "Operational",
  degraded: "Degraded",
  unavailable: "API unreachable",
};

export function HealthIndicator({ health, compact = false }: { health: HealthHandle; compact?: boolean }) {
  const pop = usePopover<HTMLDivElement>();
  const { report, state } = health;
  return (
    <div className="health" ref={pop.root}>
      <button
        type="button"
        className={`health__trigger is-${state}`}
        aria-expanded={pop.open}
        aria-haspopup="dialog"
        aria-label={`Service health: ${LABEL[state]}`}
        onClick={pop.toggle}
      >
        <span className={`dot dot--${state}`} aria-hidden="true" />
        {compact ? null : <span>{LABEL[state]}</span>}
      </button>
      {pop.open ? (
        <div className="popover health__pop" role="dialog" aria-label="Service health">
          <div className="health__pop-head">
            <strong>{LABEL[state]}</strong>
            <Button size="sm" variant="ghost" icon="refresh" loading={health.checking} onClick={health.check}>
              Check
            </Button>
          </div>
          <dl className="health__list">
            <div>
              <dt>API</dt>
              <dd className={report?.live ? "is-ready" : report ? "is-unavailable" : ""}>{report ? (report.live ? "Live" : "Not responding") : "…"}</dd>
            </div>
            <div>
              <dt>Readiness</dt>
              <dd className={report?.ready ? "is-ready" : report ? "is-degraded" : ""}>
                {report ? (report.ready ? "Ready" : report.readyReachable ? "Not ready" : "Unknown") : "…"}
              </dd>
            </div>
            {report?.checks.map((c) => (
              <div key={c.name}>
                <dt className="mono">{c.name}</dt>
                <dd className={`is-${c.state}`} title={c.detail ?? undefined}>
                  {c.state === "ready" ? "Ready" : c.state === "degraded" ? c.detail ?? "Degraded" : c.detail ?? "Unavailable"}
                </dd>
              </div>
            ))}
          </dl>
          <p className="health__foot">
            <span className="mono">{API_BASE_URL}</span>
            {report ? <span>checked {new Date(report.checkedAt).toLocaleTimeString("en-US")}</span> : null}
          </p>
        </div>
      ) : null}
    </div>
  );
}
