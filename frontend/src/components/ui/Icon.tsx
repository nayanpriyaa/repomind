const PATHS = {
  folder: "M3.5 7.5a2 2 0 0 1 2-2h3.8l2 2h7.2a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z",
  check: "M5 12.5l4.5 4.5L19 7.5",
  checkCircle: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z M8 12.3l2.7 2.7L16.2 9.5",
  alert: "M12 4 2.8 19.5h18.4Z M12 10v4.5 M12 17.3v.2",
  x: "M6 6l12 12M18 6 6 18",
  search: "M17 11a6 6 0 1 1-12 0 6 6 0 0 1 12 0Z M15.5 15.5 20 20",
  file: "M13.5 3.5H7a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9z M13.5 3.5V9H19",
  chevronDown: "M6.5 9.5 12 15l5.5-5.5",
  chevronRight: "M9.5 6.5 15 12l-5.5 5.5",
  chevronLeft: "M14.5 6.5 9 12l5.5 5.5",
  refresh: "M19.5 12a7.5 7.5 0 1 1-2.2-5.3 M19.5 4.5v4.5H15",
  pulse: "M3 12h4l2.5-6 5 12 2.5-6h4",
  panelRight: "M4 5h16v14H4z M15 5v14",
  panelLeft: "M4 5h16v14H4z M9 5v14",
  clock: "M12 20.5a8.5 8.5 0 1 0 0-17 8.5 8.5 0 0 0 0 17Z M12 7.5V12l3 2",
  layers: "M12 3.5 3.5 8l8.5 4.5L20.5 8z M3.5 12.5 12 17l8.5-4.5 M3.5 16.5 12 21l8.5-4.5",
  enter: "M9 10 4.5 14.5 9 19 M19.5 4.5V11a3.5 3.5 0 0 1-3.5 3.5H4.5",
  list: "M9 6.5h11M9 12h11M9 17.5h11 M4.5 6.5h.01M4.5 12h.01M4.5 17.5h.01",
  question: "M4.5 5.5h15v10h-9l-4.5 4v-4h-1.5z",
  scan: "M4 8.5V5.5a1.5 1.5 0 0 1 1.5-1.5h3 M15.5 4h3A1.5 1.5 0 0 1 20 5.5v3 M20 15.5v3a1.5 1.5 0 0 1-1.5 1.5h-3 M8.5 20h-3A1.5 1.5 0 0 1 4 18.5v-3 M7.5 12h9",
  info: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z M12 11v5 M12 7.8v.2",
  plus: "M12 5v14M5 12h14",
  upload: "M12 16.5V4.5 M7.5 9 12 4.5 16.5 9 M4.5 15v3.5a1.5 1.5 0 0 0 1.5 1.5h12a1.5 1.5 0 0 0 1.5-1.5V15",
  trash: "M4.5 7h15 M9.5 7V4.5h5V7 M6.5 7l1 12.5h9L17.5 7",
  copy: "M9 9h10.5v10.5H9z M15 9V4.5H4.5V15H9",
  sliders: "M4 7h9 M17 7h3 M4 17h3 M11 17h9 M15 5v4 M9 15v4",
  menu: "M4 7h16M4 12h16M4 17h16",
  database: "M12 8.5c4.1 0 7.5-1.3 7.5-3S16.1 2.5 12 2.5 4.5 3.8 4.5 5.5s3.4 3 7.5 3Z M4.5 5.5v13c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-13 M4.5 12c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3",
  code: "M8.5 7.5 4 12l4.5 4.5 M15.5 7.5 20 12l-4.5 4.5",
  shield: "M12 3.5 5 6.5v5c0 4.3 3 7.8 7 9 4-1.2 7-4.7 7-9v-5z",
  marker: "M5 12h14 M5 7h8 M5 17h11",
} as const;

export type IconName = keyof typeof PATHS;

interface IconProps {
  name: IconName;
  size?: number;
  className?: string;
  label?: string;
}

export function Icon({ name, size = 16, className, label }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className ? `icon ${className}` : "icon"}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
