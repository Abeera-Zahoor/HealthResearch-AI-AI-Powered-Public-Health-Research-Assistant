import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api";
import { AgentProgress } from "./components/AgentProgress";
import { HistoryPanel } from "./components/HistoryPanel";
import { QuestionForm } from "./components/QuestionForm";
import { ReportView } from "./components/ReportView";
import type { Health, ResearchRun, RunRequest, RunSummary } from "./types";

const POLL_MS = 1500;
const isActive = (run: ResearchRun | null) => run !== null && (run.status === "queued" || run.status === "running");
const message = (error: unknown) => (error instanceof ApiError || error instanceof Error ? error.message : "Something went wrong.");

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [history, setHistory] = useState<RunSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [run, setRun] = useState<ResearchRun | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshHistory = useCallback(async () => {
    try {
      setHistory(await api.listRuns());
    } catch {
      /* the health banner already explains connection problems */
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    api
      .health()
      .then((h) => {
        setHealth(h);
        setHealthError(null);
      })
      .catch((e) => setHealthError(message(e)));
    void refreshHistory();
  }, [refreshHistory]);

  // Poll the backend while a run is in progress so each agent's progress shows up live.
  const activeId = run?.id;
  const active = isActive(run);
  useEffect(() => {
    if (!activeId || !active) return;
    let cancelled = false;
    let failures = 0;
    const timer = window.setInterval(async () => {
      try {
        const fresh = await api.getRun(activeId);
        if (cancelled) return;
        failures = 0;
        setRun(fresh);
        if (fresh.status === "completed" || fresh.status === "failed") void refreshHistory();
      } catch (e) {
        failures += 1;
        if (failures >= 5 && !cancelled) {
          window.clearInterval(timer);
          setError(`Lost contact with the backend while the run was in progress. ${message(e)}`);
        }
      }
    }, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [activeId, active, refreshHistory]);

  const startRun = async (request: RunRequest) => {
    setError(null);
    setSubmitting(true);
    try {
      const created = await api.startRun(request);
      setRun(created);
      void refreshHistory();
    } catch (e) {
      setError(message(e));
    } finally {
      setSubmitting(false);
    }
  };

  const openRun = async (id: string) => {
    setError(null);
    try {
      setRun(await api.getRun(id));
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      setError(message(e));
      void refreshHistory();
    }
  };

  const deleteRun = async (id: string) => {
    if (!window.confirm("Delete this research run from your history?")) return;
    try {
      await api.deleteRun(id);
      if (run?.id === id) setRun(null);
      await refreshHistory();
    } catch (e) {
      setError(message(e));
    }
  };

  const busy = submitting || active;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">+</span>
          <div>
            <h1>HealthResearch AI</h1>
            <p>Multi-agent public health research assistant</p>
          </div>
        </div>
        <div className="status-pills">
          {health ? (
            <>
              <span className="pill pill-ok">Backend connected</span>
              <span className={health.llm.enabled ? "pill pill-ok" : "pill pill-warn"} title={health.llm_problem ?? undefined}>
                {health.llm.enabled ? `AI: ${health.llm.provider} / ${health.llm.model}` : "No AI provider - extractive mode"}
              </span>
            </>
          ) : healthError ? (
            <span className="pill pill-bad">Backend offline</span>
          ) : (
            <span className="pill">Connecting...</span>
          )}
        </div>
      </header>

      <div className="layout">
        <aside className="sidebar">
          <details className="sidebar-details" open>
            <summary className="sidebar-summary">Research history ({history.length})</summary>
            <HistoryPanel
              runs={history}
              activeId={run?.id ?? null}
              loading={historyLoading}
              onOpen={openRun}
              onDelete={deleteRun}
              onNew={() => {
                setRun(null);
                setError(null);
              }}
            />
          </details>
        </aside>

        <main className="main">
          {healthError && (
            <div className="notice notice-bad" role="alert">
              <strong>The backend is not reachable.</strong> {healthError}
            </div>
          )}
          {health?.llm_problem && (
            <div className="notice notice-warn" role="note">
              <strong>AI writing is switched off.</strong> {health.llm_problem} The app still works in extractive mode using abstract text only.
            </div>
          )}

          <QuestionForm busy={busy} sampleQuestion={health?.sample_question ?? "Does regular physical activity reduce the risk of depression in adults?"} onSubmit={startRun} />

          {error && (
            <div className="notice notice-bad" role="alert">
              <strong>Something went wrong.</strong> {error}
            </div>
          )}

          {run && <AgentProgress steps={run.steps} />}

          {run?.status === "failed" && run.error && (
            <div className="notice notice-bad" role="alert">
              <strong>The workflow stopped.</strong> {run.error}
            </div>
          )}

          {run && !active && <ReportView key={run.id} run={run} />}

          {!run && !error && (
            <section className="card intro">
              <h2 className="card-title">How it works</h2>
              <ol className="intro-list">
                <li><strong>Research Agent</strong> retrieves real papers from PubMed and Europe PMC.</li>
                <li><strong>Evidence Analysis Agent</strong> summarises findings, gaps and limitations.</li>
                <li><strong>Citation Verification Agent</strong> checks every reference and flags claims it cannot verify.</li>
                <li><strong>Health Education Agent</strong> writes your chosen output from the verified evidence only.</li>
              </ol>
              <p className="muted small">No paper, number or link is ever invented: references come straight from the databases, and anything that cannot be verified is flagged.</p>
            </section>
          )}
        </main>
      </div>
      <footer className="footer">Educational tool - not medical advice. Always check the linked sources.</footer>
    </div>
  );
}
