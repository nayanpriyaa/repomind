import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import "./ui.css";

interface NoticeProps {
  tone?: "neutral" | "error";
  icon?: IconName;
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
}

export function Notice({ tone = "neutral", icon, title, children, actions }: NoticeProps) {
  return (
    <div className={`notice notice--${tone}`} role={tone === "error" ? "alert" : undefined}>
      <span className="notice__icon">
        <Icon name={icon ?? (tone === "error" ? "alert" : "info")} />
      </span>
      <p className="notice__title">{title}</p>
      {children ? <div className="notice__body">{children}</div> : null}
      {actions ? <div className="notice__actions">{actions}</div> : null}
    </div>
  );
}
