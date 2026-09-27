import { useMemo } from "react";
import type { Investigation } from "../../hooks/useInvestigations";
import { countUnmatchedRefs, parseAnswer } from "../../lib/citations";
import { formatDuration, formatNumber, modeLabel } from "../../lib/format";
import { RETRIEVAL_MODES, type QueryResponse, type RetrievalMode } from "../../types/api";
import { Citation } from "../citations/Citation";
import { ApiErrorNotice } from "../ui/ApiErrorNotice";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { AnswerText } from "./AnswerText";
import "./answer.css";

interface AnswerViewProps {
  investigation: Investigation;
  selectedIndex: number | null;
  onSelectSource: (index: number) => void;
  onRetry: () => void;
  onAskWithMode: (mode: RetrievalMode) => void;
  onInspectRetrieval: () => void;
}

export function AnswerView({ investigation, selectedIndex, onSelectSource, onRetry, onAskWithMode, onInspectRetrieval }: AnswerViewProps) {
  const { result } = investigation;
  return (
    <article className="answer" aria-live="polite" aria-busy={result.status === "loading"}>
      <header className="answer__question">
        <h2>{investigation.question}</h2>
        <p className="answer__asked">
          <span className="mono">{investigation.repositoryId}</span>
          <span>{modeLabel(investigation.mode)} retrieval</span>
          <span>top {investigation.topK}</span>
          {result.status === "done" ? <span>{formatDuration(result.durationMs)}</span> : null}
        </p>
      </header>

      {result.status === "loading" ? <AnswerLoading /> : null}
      {result.status === "error" ? (
        <ApiErrorNotice title="Unable to query repository" error={result.error} onRetry={onRetry} />
      ) : null}
      {result.status === "done" ? (
        <AnswerBody
          response={result.response}
          askedMode={investigation.mode}
          selectedIndex={selectedIndex}
          onSelectSource={onSelectSource}
          onAskWithMode={onAskWithMode}
          onInspectRetrieval={onInspectRetrieval}
        />
      ) : null}
    </article>
  );
}

function AnswerLoading() {
  return (
    <div className="answer__loading">
      <p className="answer__status">
        <span className="spinner" aria-hidden="true" />
        Retrieving chunks and generating a grounded answer
      </p>
      <div className="answer__skeleton" aria-hidden="true">
        <span className="skeleton" style={{ width: "92%" }} />
        <span className="skeleton" style={{ width: "86%" }} />
        <span className="skeleton" style={{ width: "58%" }} />
      </div>
    </div>
  );
}

interface AnswerBodyProps {
  response: QueryResponse;
  askedMode: RetrievalMode;
  selectedIndex: number | null;
  onSelectSource: (index: number) => void;
  onAskWithMode: (mode: RetrievalMode) => void;
  onInspectRetrieval: () => void;
}

function AnswerBody({ response, askedMode, selectedIndex, onSelectSource, onAskWithMode, onInspectRetrieval }: AnswerBodyProps) {
  const blocks = useMemo(() => parseAnswer(response.answer, response.sources), [response]);
  const unmatched = countUnmatchedRefs(blocks);
  const refCounts = useMemo(() => {
    const counts = new Map<number, number>();
    for (const b of blocks) for (const s of b.segments) if (s.kind === "ref" && s.sourceIndex !== null) counts.set(s.sourceIndex, (counts.get(s.sourceIndex) ?? 0) + 1);
    return counts;
  }, [blocks]);

  const sources = response.sources.length ? (
    <section className="sources" aria-label="Sources">
      <header className="sources__head">
        <h3>{response.grounded ? "Evidence" : "Retrieved chunks"}</h3>
        <span>{response.sources.length} ranked by retrieval score</span>
      </header>
      <div className="sources__list">
        {response.sources.map((s, i) => (
          <Citation
            key={`${s.file_path}:${s.start_line}:${i}`}
            source={s}
            position={i + 1}
            selected={selectedIndex === i}
            referenced={refCounts.get(i) ?? 0}
            onSelect={() => onSelectSource(i)}
          />
        ))}
      </div>
    </section>
  ) : null;

  if (!response.grounded) {
    const otherModes = RETRIEVAL_MODES.filter((m) => m !== askedMode);
    return (
      <>
        <section className="insufficient" aria-label="Insufficient evidence">
          <header className="insufficient__head">
            <Icon name="info" size={16} />
            <h3>Insufficient evidence</h3>
          </header>
          <p className="insufficient__lead">
            RepoMind couldn't find enough repository evidence to answer this question confidently.
          </p>
          {response.answer ? (
            <div className="insufficient__model">
              <p className="insufficient__label">Model response, not verified against sources</p>
              <AnswerText blocks={blocks} selectedIndex={selectedIndex} onSelect={onSelectSource} muted />
            </div>
          ) : null}
          <div className="insufficient__try">
            <p>Try:</p>
            <ul>
              <li>using a more specific identifier, such as a class or function name</li>
              <li>switching retrieval mode</li>
              <li>asking about a specific file or symbol</li>
            </ul>
          </div>
          <div className="insufficient__actions">
            {otherModes.map((m) => (
              <Button key={m} size="sm" onClick={() => onAskWithMode(m)}>
                Ask again with {modeLabel(m)}
              </Button>
            ))}
            <Button size="sm" variant="ghost" icon="list" onClick={onInspectRetrieval}>
              Inspect retrieval
            </Button>
          </div>
        </section>
        {sources}
      </>
    );
  }

  return (
    <>
      <div className="grounding" role="status">
        <span className="grounding__mark">
          <Icon name="checkCircle" size={15} />
          Grounded in {response.chunks_used} source {response.chunks_used === 1 ? "chunk" : "chunks"}
        </span>
        {response.context_characters !== null ? (
          <span className="grounding__meta">{formatNumber(response.context_characters)} characters of context</span>
        ) : null}
      </div>
      {response.answer ? (
        <AnswerText blocks={blocks} selectedIndex={selectedIndex} onSelect={onSelectSource} />
      ) : (
        <p className="answer__empty">The API reported a grounded result but returned no answer text.</p>
      )}
      {unmatched > 0 ? (
        <p className="answer__unmatched">
          <Icon name="alert" size={14} />
          {unmatched === 1 ? "1 reference in this answer doesn't" : `${unmatched} references in this answer don't`} match a retrieved source. Verify{" "}
          {unmatched === 1 ? "it" : "them"} manually.
        </p>
      ) : null}
      {sources}
    </>
  );
}
