import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnswerView } from "./components/answer/AnswerView";
import { IndexingPanel } from "./components/indexing/IndexingPanel";
import { Onboarding } from "./components/indexing/Onboarding";
import { TopBar } from "./components/layout/TopBar";
import { Composer } from "./components/query/Composer";
import { ExampleQuestions } from "./components/query/ExampleQuestions";
import { RepositoryRail } from "./components/repository/RepositoryRail";
import { RetrievalView } from "./components/retrieval/RetrievalView";
import { EvidencePanel } from "./components/source-viewer/EvidencePanel";
import { ApiErrorNotice } from "./components/ui/ApiErrorNotice";
import { Button } from "./components/ui/Button";
import { Drawer } from "./components/ui/Drawer";
import { Icon } from "./components/ui/Icon";
import { Notice } from "./components/ui/Notice";
import { useEvidence } from "./hooks/useEvidence";
import { useHealth } from "./hooks/useHealth";
import { useHotkeys } from "./hooks/useHotkeys";
import { useIndexing } from "./hooks/useIndexing";
import { useUpload } from "./hooks/useUpload";
import { useInvestigations } from "./hooks/useInvestigations";
import { useMediaQuery } from "./hooks/useMediaQuery";
import { useRepositories, useRepositoryStatus } from "./hooks/useRepositories";
import { useRetrieval } from "./hooks/useRetrieval";
import { deleteRepository } from "./services/repositories";
import type { RepositorySummary, RetrievalMode } from "./types/api";
import "./components/layout/layout.css";

type View = "ask" | "retrieval";

export default function App() {
  const health = useHealth();
  const repos = useRepositories();
  const [statusRevision, setStatusRevision] = useState(0);
  const repoStatus = useRepositoryStatus(repos.selectedId, statusRevision);
  const investigations = useInvestigations();
  const retrieval = useRetrieval();
  const evidence = useEvidence();

  const [view, setView] = useState<View>("ask");
  const [addingRepository, setAddingRepository] = useState(false);
  const [mode, setMode] = useState<RetrievalMode>("hybrid");
  const [topK, setTopK] = useState(5);
  const [draft, setDraft] = useState("");
  const [railOpen, setRailOpen] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const isWide = useMediaQuery("(min-width: 1280px)");
  const isMedium = useMediaQuery("(min-width: 820px)");
  const composerRef = useRef<HTMLTextAreaElement>(null);

  const { reload, select } = repos;
  const onIndexed = useCallback(
    (id: string) => {
      void reload().then(() => select(id));
      setStatusRevision((r) => r + 1);
    },
    [reload, select],
  );
  const indexing = useIndexing(onIndexed);

  // A finished upload refreshes the list and selects the new repository, so the
  // user lands on it ready to index.
  const onUploaded = useCallback(
    (repository: RepositorySummary) => {
      void reload().then(() => select(repository.id));
      setAddingRepository(false);
      setStatusRevision((r) => r + 1);
    },
    [reload, select],
  );
  const upload = useUpload(onUploaded);

  const selected = repos.selected;
  const selectedId = repos.selectedId;

  // Results are bound to the repository they were produced for; never show them under another repository.
  const activeInvestigation =
    investigations.active && investigations.active.repositoryId === selectedId ? investigations.active : null;
  const retrievalRun = retrieval.run && retrieval.run.repositoryId === selectedId ? retrieval.run : null;
  const history = useMemo(
    () => investigations.items.filter((i) => i.repositoryId === selectedId),
    [investigations.items, selectedId],
  );

  const effectiveStatus =
    indexing.state.phase === "running" && indexing.state.repositoryId === selectedId
      ? "indexing"
      : repoStatus.status && repoStatus.status.status !== "unknown"
        ? repoStatus.status.status
        : selected?.status ?? "unknown";

  const selectRepository = useCallback(
    (id: string) => {
      if (id !== selectedId) {
        evidence.clear();
        retrieval.clear();
        investigations.open(null);
      }
      select(id);
      setAddingRepository(false);
      setRailOpen(false);
    },
    [evidence, investigations, retrieval, select, selectedId],
  );

  const startIndexing = useCallback(
    (id: string, force = false) => {
      setAddingRepository(false);
      setRailOpen(false);
      indexing.start(id, force);
    },
    [indexing],
  );

  const removeRepository = useCallback(
    (id: string) => {
      if (!window.confirm(`Delete ${id}? Its files and index entries are removed from the server.`)) return;
      void deleteRepository(id)
        .catch(() => undefined)
        .then(() => reload())
        .then((list) => {
          evidence.clear();
          retrieval.clear();
          investigations.open(null);
          select(list?.[0]?.id ?? null);
          setRailOpen(false);
        });
    },
    [evidence, investigations, reload, retrieval, select],
  );

  // Close the evidence drawer automatically when the layout gains a dedicated column.
  useEffect(() => {
    if (isWide) setEvidenceOpen(false);
    if (isMedium) setRailOpen(false);
  }, [isWide, isMedium]);

  const revealEvidence = useCallback(() => {
    if (!isWide) setEvidenceOpen(true);
  }, [isWide]);

  const selectAnswerSource = useCallback(
    (index: number) => {
      if (!activeInvestigation || activeInvestigation.result.status !== "done") return;
      const sources = activeInvestigation.result.response.sources;
      const source = sources[index];
      if (!source) return;
      evidence.select({
        contextId: activeInvestigation.id,
        source,
        position: index + 1,
        total: sources.length,
        rank: index + 1,
        matchType: activeInvestigation.result.response.mode,
        retrieved: null,
        lookup: {
          repositoryId: activeInvestigation.repositoryId,
          query: activeInvestigation.question,
          mode: activeInvestigation.mode,
          topK: Math.max(activeInvestigation.topK, sources.length),
        },
      });
      revealEvidence();
    },
    [activeInvestigation, evidence, revealEvidence],
  );

  const selectRetrievalResult = useCallback(
    (index: number) => {
      if (!retrievalRun || retrievalRun.result.status !== "done") return;
      const results = retrievalRun.result.response.results;
      const r = results[index];
      if (!r) return;
      evidence.select({
        contextId: retrievalRun.id,
        source: r,
        position: index + 1,
        total: results.length,
        rank: r.rank,
        matchType: r.match_type,
        retrieved: r,
        lookup: null,
      });
      revealEvidence();
    },
    [evidence, retrievalRun, revealEvidence],
  );

  const stepEvidence = useCallback(
    (delta: -1 | 1) => {
      const sel = evidence.selection;
      if (!sel) {
        if (view === "ask") selectAnswerSource(0);
        else selectRetrievalResult(0);
        return;
      }
      const next = sel.position - 1 + delta;
      if (next < 0 || next >= sel.total) return;
      if (activeInvestigation && sel.contextId === activeInvestigation.id) selectAnswerSource(next);
      else if (retrievalRun && sel.contextId === retrievalRun.id) selectRetrievalResult(next);
    },
    [activeInvestigation, evidence.selection, retrievalRun, selectAnswerSource, selectRetrievalResult, view],
  );

  const ask = useCallback(
    (question: string, withMode: RetrievalMode = mode) => {
      if (!selectedId || !question.trim()) return;
      evidence.clear();
      investigations.ask({ repositoryId: selectedId, question: question.trim(), mode: withMode, topK });
    },
    [evidence, investigations, mode, selectedId, topK],
  );

  const runSearch = useCallback(
    (query: string, withMode: RetrievalMode = mode) => {
      if (!selectedId || !query.trim()) return;
      evidence.clear();
      retrieval.search({ repositoryId: selectedId, query: query.trim(), mode: withMode, topK });
    },
    [evidence, mode, retrieval, selectedId, topK],
  );

  const onSubmit = (): void => {
    if (view === "ask") {
      ask(draft);
      setDraft("");
    } else runSearch(draft);
  };

  useHotkeys({
    "/": (e) => {
      e.preventDefault();
      composerRef.current?.focus();
    },
    "[": () => stepEvidence(-1),
    "]": () => stepEvidence(1),
  });

  const selectedAnswerIndex =
    evidence.selection && activeInvestigation && evidence.selection.contextId === activeInvestigation.id
      ? evidence.selection.position - 1
      : null;
  const selectedRetrievalIndex =
    evidence.selection && retrievalRun && evidence.selection.contextId === retrievalRun.id ? evidence.selection.position - 1 : null;
  const evidenceContextVisible =
    evidence.selection !== null &&
    ((view === "ask" && selectedAnswerIndex !== null) || (view === "retrieval" && selectedRetrievalIndex !== null));

  const composerBusy =
    view === "ask" ? activeInvestigation?.result.status === "loading" : retrievalRun?.result.status === "loading";
  const notReadyReason =
    effectiveStatus === "indexing" ? "Indexing in progress" : effectiveStatus === "not_indexed" || effectiveStatus === "failed" ? "Index this repository first" : undefined;

  const workspaceReady =
    repos.loadState !== "loading" && indexing.state.phase === "idle" && !addingRepository && selected !== null && !(repos.loadState === "error" && repos.error);
  const evidenceColumn = isWide && workspaceReady;

  const rail = (
    <RepositoryRail
      repos={repos}
      status={repoStatus}
      indexing={indexing.state}
      history={history}
      activeInvestigationId={activeInvestigation?.id ?? null}
      onOpenInvestigation={(id) => {
        investigations.open(id);
        evidence.clear();
        setView("ask");
        setRailOpen(false);
      }}
      onUploadNew={() => {
        setAddingRepository(true);
        setRailOpen(false);
      }}
      onReindex={startIndexing}
      onDelete={removeRepository}
      onSelectRepository={selectRepository}
    />
  );

  const evidencePanel = (
    <EvidencePanel
      selection={evidenceContextVisible ? evidence.selection : null}
      excerpt={evidenceContextVisible ? evidence.excerpt : null}
      onRetry={evidence.retryExcerpt}
      onStep={stepEvidence}
    />
  );

  const renderWorkspace = () => {
    if (repos.loadState === "loading" && repos.repositories.length === 0) {
      return (
        <div className="workspace__skeleton" aria-busy="true" aria-label="Loading repositories">
          <span className="skeleton" />
          <span className="skeleton" />
          <span className="skeleton" />
        </div>
      );
    }
    if (indexing.state.phase !== "idle") {
      const retryId = indexing.state.repositoryId;
      return <IndexingPanel state={indexing.state} health={health.report} onRetry={() => startIndexing(retryId)} onDismiss={indexing.dismiss} />;
    }
    if (repos.loadState === "error" && repos.error) {
      return (
        <div className="workspace__notready">
          <ApiErrorNotice title="Unable to load repositories" error={repos.error} onRetry={() => void repos.reload()} />
        </div>
      );
    }
    if (addingRepository || !selected) {
      return (
        <Onboarding
          repositories={repos.repositories}
          upload={upload.state}
          onUpload={upload.upload}
          onSelect={selectRepository}
          onCancel={selected ? () => setAddingRepository(false) : undefined}
        />
      );
    }

    return (
      <>
        <div className="workspace__composer">
          <div className="ws-context">
            <p className="ws-context__repo">
              <Icon name="folder" size={14} />
              <strong>{selected.name}</strong>
              <span className="ws-context__path mono">{selected.id}</span>
            </p>
            <div className="tabs" role="tablist" aria-label="Workspace mode">
              <button type="button" role="tab" aria-selected={view === "ask"} onClick={() => setView("ask")}>
                <Icon name="question" size={14} />
                Ask
              </button>
              <button type="button" role="tab" aria-selected={view === "retrieval"} onClick={() => setView("retrieval")}>
                <Icon name="list" size={14} />
                Retrieval
              </button>
            </div>
          </div>
          <Composer
            ref={composerRef}
            repositoryName={selected.name}
            value={draft}
            onChange={setDraft}
            mode={mode}
            onModeChange={setMode}
            topK={topK}
            onTopKChange={setTopK}
            onSubmit={onSubmit}
            busy={Boolean(composerBusy)}
            disabled={Boolean(notReadyReason)}
            disabledReason={notReadyReason}
            submitLabel={view === "ask" ? "Ask" : "Retrieve"}
            placeholder={view === "ask" ? `Ask where authentication is implemented in ${selected.name}…` : "Search chunks without generating an answer…"}
          />
        </div>

        <div className="workspace__content" role="tabpanel">
          {notReadyReason === "Index this repository first" ? (
            <Notice
              title={effectiveStatus === "failed" ? "The last index run for this repository failed" : "This repository isn't indexed yet"}
              actions={
                <Button size="sm" variant="primary" icon="scan" onClick={() => startIndexing(selected.id)}>
                  Index repository
                </Button>
              }
            >
              <p>Questions can only be answered from an index. Indexing reads files; it doesn't run them.</p>
            </Notice>
          ) : null}

          {view === "ask" ? (
            activeInvestigation ? (
              <AnswerView
                investigation={activeInvestigation}
                selectedIndex={selectedAnswerIndex}
                onSelectSource={selectAnswerSource}
                onRetry={() => investigations.retry(activeInvestigation.id)}
                onAskWithMode={(m) => {
                  setMode(m);
                  ask(activeInvestigation.question, m);
                }}
                onInspectRetrieval={() => {
                  setView("retrieval");
                  setDraft(activeInvestigation.question);
                  runSearch(activeInvestigation.question, activeInvestigation.mode);
                }}
              />
            ) : !notReadyReason ? (
              <ExampleQuestions
                onPick={(q) => {
                  setDraft(q);
                  composerRef.current?.focus();
                }}
              />
            ) : null
          ) : (
            <RetrievalView
              run={retrievalRun}
              selectedIndex={selectedRetrievalIndex}
              onSelect={selectRetrievalResult}
              onRetry={() => retrievalRun && runSearch(retrievalRun.query, retrievalRun.mode)}
            />
          )}
        </div>
      </>
    );
  };

  return (
    <div className="app">
      <TopBar
        health={health}
        repositoryName={selected?.name ?? null}
        showRailToggle={!isMedium}
        showEvidenceToggle={!isWide && workspaceReady}
        evidenceActive={evidenceContextVisible}
        onOpenRail={() => setRailOpen(true)}
        onOpenEvidence={() => setEvidenceOpen(true)}
      />
      <div className={`app__body${isMedium ? " has-rail" : ""}${evidenceColumn ? " has-evidence" : ""}`}>
        {isMedium ? <aside className="app__rail">{rail}</aside> : null}
        <main className="workspace">
          <div className="workspace__inner">{renderWorkspace()}</div>
        </main>
        {evidenceColumn ? <aside className="app__evidence">{evidencePanel}</aside> : null}
      </div>
      {!isMedium ? (
        <Drawer open={railOpen} side="left" title="Repository" onClose={() => setRailOpen(false)}>
          {rail}
        </Drawer>
      ) : null}
      {!isWide ? (
        <Drawer open={evidenceOpen} side="right" title="Evidence" onClose={() => setEvidenceOpen(false)}>
          {evidencePanel}
        </Drawer>
      ) : null}
    </div>
  );
}
