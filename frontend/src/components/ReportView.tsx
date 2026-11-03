import { useMemo, useState } from "react";
import { downloadText, runToMarkdown } from "../lib/exportMarkdown";
import { audienceLabel, outputLabel } from "../lib/format";
import type { Paper, ResearchRun } from "../types";
import { EvidencePanel, OutputPanel, ReferencesPanel, VerificationPanel } from "./panels";

type Tab = "output" | "evidence" | "verification" | "references";

export function ReportView({ run }: { run: ResearchRun }) {
  const [tab, setTab] = useState<Tab>("output");
  const papers = useMemo(() => new Map<string, Paper>(run.papers.map((p) => [p.ref_id, p])), [run.papers]);
  const flagged = (run.citations?.counts.claims_unsupported ?? 0) + (run.citations?.counts.references_flagged ?? 0);

  const tabs: { id: Tab; label: string; count?: number }[] = [
    { id: "output", label: "Report" },
    { id: "evidence", label: "Evidence", count: run.analysis?.findings.length },
    { id: "verification", label: "Verification", count: flagged || undefined },
    { id: "references", label: "References", count: run.papers.length },
  ];

  return (
    <section className="card report" aria-label="Research report">
      <div className="report-head">
        <div>
          <h2 className="card-title">{run.question}</h2>
          <p className="muted small">
            {audienceLabel(run.audience)} - {outputLabel(run.output_type)} - {run.llm.enabled ? `AI: ${run.llm.provider} (${run.llm.model})` : "No AI provider (extractive mode)"}
          </p>
        </div>
        {run.status === "completed" && run.papers.length > 0 && (
          <button type="button" className="secondary" onClick={() => downloadText(`healthresearch-${run.id}.md`, runToMarkdown(run))}>
            Download .md
          </button>
        )}
      </div>

      {run.warnings.length > 0 && (
        <div className="notice notice-warn" role="note">
          <strong>Heads up</strong>
          <ul className="plain-list">
            {run.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {run.papers.length === 0 ? (
        <p className="muted">No papers were retrieved, so there is no report to show.</p>
      ) : (
        <>
          <div className="tabs" role="tablist">
            {tabs.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={tab === t.id}
                className={tab === t.id ? "tab active" : "tab"}
                onClick={() => setTab(t.id)}
              >
                {t.label}
                {t.count !== undefined && <span className="tab-count">{t.count}</span>}
              </button>
            ))}
          </div>
          <div className="tab-panel" role="tabpanel">
            {tab === "output" && <OutputPanel run={run} papers={papers} />}
            {tab === "evidence" && <EvidencePanel run={run} papers={papers} />}
            {tab === "verification" && <VerificationPanel run={run} />}
            {tab === "references" && <ReferencesPanel run={run} />}
          </div>
        </>
      )}
    </section>
  );
}
