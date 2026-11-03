import { durationSeconds } from "../lib/format";
import type { AgentStep, StepStatus } from "../types";

const ICON: Record<StepStatus, string> = {
  pending: "",
  running: "",
  completed: "✓",
  failed: "✕",
  skipped: "–",
};

const DESCRIPTION: Record<string, string> = {
  research: "Finds real papers in PubMed and Europe PMC",
  analysis: "Summarises findings, gaps and limitations",
  verification: "Checks references and flags unsupported claims",
  education: "Writes the output from verified evidence only",
};

export function AgentProgress({ steps }: { steps: AgentStep[] }) {
  return (
    <section className="card" aria-label="Agent progress">
      <h2 className="card-title">Agent workflow</h2>
      <ol className="steps">
        {steps.map((step, index) => {
          const seconds = durationSeconds(step.started_at, step.finished_at);
          return (
            <li key={step.key} className={`step step-${step.status}`}>
              <span className="step-marker" aria-hidden="true">
                {step.status === "running" ? <span className="spinner dark" /> : ICON[step.status] || index + 1}
              </span>
              <div className="step-body">
                <div className="step-title">
                  <strong>{step.name}</strong>
                  <span className="step-status">{step.status}</span>
                  {seconds !== null && <span className="muted small">{seconds}s</span>}
                </div>
                <div className="muted small">{step.message || DESCRIPTION[step.key]}</div>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
