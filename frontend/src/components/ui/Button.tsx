import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import "./ui.css";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "primary" | "ghost";
  size?: "md" | "sm";
  icon?: IconName;
  iconOnly?: boolean;
  loading?: boolean;
  children?: ReactNode;
}

export function Button({
  variant = "default",
  size = "md",
  icon,
  iconOnly = false,
  loading = false,
  className,
  children,
  type = "button",
  ...rest
}: ButtonProps) {
  const classes = [
    "btn",
    variant !== "default" && `btn--${variant}`,
    size === "sm" && "btn--sm",
    iconOnly && "btn--icon",
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <button type={type} className={classes} aria-busy={loading || undefined} {...rest}>
      {loading ? <span className="spinner" aria-hidden="true" /> : icon ? <Icon name={icon} size={size === "sm" ? 14 : 16} /> : null}
      {iconOnly ? null : children}
    </button>
  );
}
