import { Fragment, type ReactElement } from "react";
import type { AnswerBlock } from "../../lib/citations";
import { InlineRef } from "../citations/Citation";

interface AnswerTextProps {
  blocks: readonly AnswerBlock[];
  selectedIndex: number | null;
  onSelect: (sourceIndex: number) => void;
  muted?: boolean;
}

export function AnswerText({ blocks, selectedIndex, onSelect, muted = false }: AnswerTextProps) {
  const rendered: ReactElement[] = [];
  let bullets: ReactElement[] = [];
  const flushBullets = (key: number): void => {
    if (bullets.length) {
      rendered.push(<ul key={`ul-${key}`}>{bullets}</ul>);
      bullets = [];
    }
  };

  blocks.forEach((block, i) => {
    const content = block.segments.map((seg, j) => {
      if (seg.kind === "text") return <Fragment key={j}>{seg.text}</Fragment>;
      if (seg.kind === "code") return <code key={j} className="answer-code mono">{seg.text}</code>;
      const idx = seg.sourceIndex;
      return (
        <InlineRef
          key={j}
          text={seg.text}
          matched={idx !== null}
          selected={idx !== null && idx === selectedIndex}
          onSelect={idx !== null ? () => onSelect(idx) : undefined}
        />
      );
    });
    if (block.kind === "bullet") bullets.push(<li key={i}>{content}</li>);
    else {
      flushBullets(i);
      rendered.push(<p key={i}>{content}</p>);
    }
  });
  flushBullets(blocks.length);

  return <div className={`answer-text${muted ? " is-muted" : ""}`}>{rendered}</div>;
}
