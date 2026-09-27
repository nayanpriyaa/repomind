import type { HealthHandle } from "../../hooks/useHealth";
import { HealthIndicator } from "../health/HealthIndicator";
import { Button } from "../ui/Button";
import "./layout.css";

interface TopBarProps {
  health: HealthHandle;
  repositoryName: string | null;
  showRailToggle: boolean;
  showEvidenceToggle: boolean;
  evidenceActive: boolean;
  onOpenRail: () => void;
  onOpenEvidence: () => void;
}

export function TopBar({ health, repositoryName, showRailToggle, showEvidenceToggle, evidenceActive, onOpenRail, onOpenEvidence }: TopBarProps) {
  return (
    <header className="topbar">
      {showRailToggle ? <Button variant="ghost" iconOnly icon="menu" aria-label="Open repository panel" onClick={onOpenRail} /> : null}
      <span className="brand">
        <svg className="brand__mark" width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
          <rect x="0.5" y="0.5" width="17" height="17" rx="3.5" fill="none" stroke="var(--border-strong)" />
          <path d="M4.5 5h4M4.5 9h9M4.5 13h5.5" stroke="var(--text-2)" strokeWidth="1.6" strokeLinecap="round" />
          <path d="M4.5 9h9" stroke="var(--marker)" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
        <span className="brand__name">RepoMind</span>
      </span>
      {showRailToggle && repositoryName ? <span className="topbar__repo mono">{repositoryName}</span> : null}
      <span className="topbar__spacer" />
      <HealthIndicator health={health} compact={showRailToggle} />
      {showEvidenceToggle ? (
        <Button
          variant="ghost"
          iconOnly={showRailToggle}
          icon="panelRight"
          aria-label="Open evidence panel"
          className={evidenceActive ? "topbar__evidence is-active" : "topbar__evidence"}
          onClick={onOpenEvidence}
        >
          Evidence
        </Button>
      ) : null}
    </header>
  );
}
