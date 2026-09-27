import { useEffect, useRef } from "react";

export interface HotkeyMap {
  [key: string]: (event: KeyboardEvent) => void;
}

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

/** Global single-key shortcuts that never fire while the user is typing. `Escape` always fires. */
export function useHotkeys(map: HotkeyMap): void {
  const ref = useRef(map);
  ref.current = map;
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key !== "Escape" && isTyping(e.target)) return;
      const handler = ref.current[e.key];
      if (handler) handler(e);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
