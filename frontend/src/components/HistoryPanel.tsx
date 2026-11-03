import { audienceLabel, formatDate, outputLabel, STATUS_LABEL } from "../lib/format";
import type { RunSummary } from "../types";

interface Props {
  runs: RunSummary[];
  activeId: string | null;
  loading: boolean;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  onNew: () => void;
}

export function HistoryPanel({ runs, activeId, loading, onOpen, onDelete, onNew }: Props) {
  return (
    <div className="history">
      <div className="history-head">
        <h2 className="card-title">Research history</h2>
        <button type="button" className="secondary small-btn" onClick={onNew}>
          + New
        </button>
      </div>
      {loading && <p className="muted small">Loading history...</p>}
      {!loading && runs.length === 0 && <p className="muted small">Your completed research is saved here automatically so you can revisit it.</p>}
      <ul className="history-list">
        {runs.map((run) => (
          <li key={run.id} className={run.id === activeId ? "history-item active" : "history-item"}>
            <button type="button" className="history-open" onClick={() => onOpen(run.id)} aria-label={`Open: ${run.question}`}>
              <span className="history-question">{run.question}</span>
              <span className="history-meta">
                <span className={`dot dot-${run.status}`} aria-hidden="true" />
                {STATUS_LABEL[run.status]} - {run.paper_count} papers - {outputLabel(run.output_type)}
              </span>
              <span className="history-meta">
                {audienceLabel(run.audience)} - {formatDate(run.created_at)}
              </span>
            </button>
            <button type="button" className="icon-button" onClick={() => onDelete(run.id)} aria-label={`Delete: ${run.question}`} title="Delete">
              {"✕"}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
