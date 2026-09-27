import type { Source } from "../types/api";
import { normalizePath } from "./guards";

export type AnswerSegment =
  | { kind: "text"; text: string }
  | { kind: "code"; text: string }
  | {
      kind: "ref";
      text: string;
      file: string;
      start: number | null;
      end: number | null;
      /** Index into the response's `sources`, or null when the answer cites something not retrieved. */
      sourceIndex: number | null;
    };

export interface AnswerBlock {
  kind: "paragraph" | "bullet";
  segments: AnswerSegment[];
}

const REF = /(?<![\w/.-])((?:[\w.-]+\/)*[\w-][\w.-]*\.[A-Za-z][A-Za-z0-9]{0,9})(?::(\d+)(?:\s*[-–—]\s*(\d+))?)?/g;

function pathsMatch(cited: string, source: string): boolean {
  const a = normalizePath(cited);
  const b = normalizePath(source);
  return a === b || b.endsWith("/" + a) || a.endsWith("/" + b);
}

export function matchSource(
  sources: readonly Source[],
  file: string,
  start: number | null,
  end: number | null,
): number | null {
  const candidates = sources
    .map((s, index) => ({ s, index }))
    .filter(({ s }) => pathsMatch(file, s.file_path));
  if (candidates.length === 0) return null;
  if (start === null) return candidates[0]?.index ?? null;
  const lo = start;
  const hi = end ?? start;
  // Prefer the exact range, then the tightest chunk containing the citation, then any overlap.
  const exact = candidates.find(({ s }) => s.start_line === lo && s.end_line === hi);
  if (exact) return exact.index;
  const span = (s: Source): number => s.end_line - s.start_line;
  const containing = candidates
    .filter(({ s }) => s.start_line <= lo && s.end_line >= hi)
    .sort((a, b) => span(a.s) - span(b.s));
  if (containing[0]) return containing[0].index;
  const overlapping = candidates.filter(({ s }) => s.start_line <= hi && s.end_line >= lo);
  return overlapping[0]?.index ?? null;
}

function parseInline(text: string, sources: readonly Source[]): AnswerSegment[] {
  const out: AnswerSegment[] = [];
  const pushText = (t: string): void => {
    if (!t) return;
    const last = out[out.length - 1];
    if (last && last.kind === "text") last.text += t;
    else out.push({ kind: "text", text: t });
  };

  const parts = text.split(/(`[^`\n]+`)/g);
  for (const part of parts) {
    if (!part) continue;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      const inner = part.slice(1, -1);
      const whole = new RegExp(`^${REF.source}$`).exec(inner);
      const ref = whole ? toRef(whole, sources) : null;
      out.push(ref ?? { kind: "code", text: inner });
      continue;
    }
    let last = 0;
    for (const m of part.matchAll(REF)) {
      const ref = toRef(m, sources);
      if (!ref || m.index === undefined) continue;
      pushText(part.slice(last, m.index));
      out.push(ref);
      last = m.index + m[0].length;
    }
    pushText(part.slice(last));
  }
  return out;
}

function toRef(m: RegExpMatchArray | RegExpExecArray, sources: readonly Source[]): AnswerSegment | null {
  const file = m[1];
  if (!file) return null;
  const start = m[2] ? Number(m[2]) : null;
  const end = m[3] ? Number(m[3]) : start;
  const sourceIndex = matchSource(sources, file, start, end);
  // Bare dotted names (e.g. `TokenService.issue`) are only refs when they match a retrieved file.
  if (start === null && sourceIndex === null) return null;
  return { kind: "ref", text: m[0], file, start, end, sourceIndex };
}

export function parseAnswer(answer: string, sources: readonly Source[]): AnswerBlock[] {
  const cleaned = answer.replace(/\*\*(.+?)\*\*/g, "$1").replace(/\r\n?/g, "\n").trim();
  if (!cleaned) return [];
  const blocks: AnswerBlock[] = [];
  let paragraph: string[] = [];
  const flush = (): void => {
    if (paragraph.length) {
      blocks.push({ kind: "paragraph", segments: parseInline(paragraph.join(" "), sources) });
      paragraph = [];
    }
  };
  for (const raw of cleaned.split("\n")) {
    const line = raw.trim();
    const bullet = /^(?:[-*•]|\d+[.)])\s+(.*)$/.exec(line);
    if (!line) flush();
    else if (bullet) {
      flush();
      blocks.push({ kind: "bullet", segments: parseInline(bullet[1] ?? "", sources) });
    } else paragraph.push(line);
  }
  flush();
  return blocks;
}

export function countUnmatchedRefs(blocks: readonly AnswerBlock[]): number {
  return blocks.reduce(
    (n, b) => n + b.segments.filter((s) => s.kind === "ref" && s.sourceIndex === null).length,
    0,
  );
}

export function sourceKey(s: Source): string {
  return `${normalizePath(s.file_path)}:${s.start_line}-${s.end_line}:${s.symbol ?? ""}`;
}
