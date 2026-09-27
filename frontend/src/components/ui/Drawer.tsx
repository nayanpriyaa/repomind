import { useEffect, useRef, type ReactNode } from "react";
import { Button } from "./Button";
import "./ui.css";

interface DrawerProps {
  open: boolean;
  side: "left" | "right";
  title: string;
  onClose: () => void;
  children: ReactNode;
}

export function Drawer({ open, side, title, onClose, children }: DrawerProps) {
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    panel.current?.focus();
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      previous?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} aria-hidden="true" />
      <div ref={panel} className={`drawer drawer--${side}`} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1}>
        <div className="drawer__head">
          <span>{title}</span>
          <Button variant="ghost" iconOnly icon="x" aria-label={`Close ${title.toLowerCase()}`} onClick={onClose} />
        </div>
        <div className="drawer__body">{children}</div>
      </div>
    </>
  );
}
