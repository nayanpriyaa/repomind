import { useEffect, useMemo, useRef } from "react";
import { tokenizeLines } from "../../lib/highlight";
import "./source-viewer.css";

interface SourceCodeProps {
  content: string;
  firstLine: number;
  language: string | null;
  highlightStart: number;
  highlightEnd: number;
  label: string;
}

export function SourceCode({ content, firstLine, language, highlightStart, highlightEnd, label }: SourceCodeProps) {
  const lines = useMemo(() => {
    const tokenized = tokenizeLines(content, language);
    // Drop a single trailing empty line produced by a final newline.
    if (tokenized.length > 1 && tokenized[tokenized.length - 1]?.length === 0) tokenized.pop();
    return tokenized;
  }, [content, language]);
  const scroller = useRef<HTMLDivElement>(null);
  const gutterWidth = String(firstLine + lines.length).length;

  useEffect(() => {
    const el = scroller.current?.querySelector<HTMLElement>(".code-line.is-marked");
    if (el && scroller.current) {
      scroller.current.scrollTop = Math.max(0, el.offsetTop - 48);
    }
  }, [content, highlightStart]);

  return (
    <div className="code" ref={scroller} tabIndex={0} role="region" aria-label={label} style={{ ["--gutter-ch" as string]: gutterWidth }}>
      <pre className="code__pre mono">
        {lines.map((tokens, i) => {
          const n = firstLine + i;
          const marked = n >= highlightStart && n <= highlightEnd;
          return (
            <div key={n} className={marked ? "code-line is-marked" : "code-line"}>
              <span className="code-line__num" aria-hidden="true">{n}</span>
              <code className="code-line__text">
                {tokens.length === 0 ? " " : tokens.map((t, j) => (
                  <span key={j} className={t.kind === "plain" ? undefined : `tok-${t.kind}`}>{t.text}</span>
                ))}
              </code>
            </div>
          );
        })}
      </pre>
    </div>
  );
}
