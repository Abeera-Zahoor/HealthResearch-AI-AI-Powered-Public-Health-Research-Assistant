import { useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { AUDIENCE_OPTIONS, OUTPUT_OPTIONS, PAPER_COUNT_OPTIONS } from "../lib/format";
import type { Audience, OutputType, RunRequest } from "../types";

const MIN_LENGTH = 10;
const MAX_LENGTH = 500;

interface Props {
  busy: boolean;
  sampleQuestion: string;
  onSubmit: (request: RunRequest) => void;
}

export function QuestionForm({ busy, sampleQuestion, onSubmit }: Props) {
  const [question, setQuestion] = useState("");
  const [audience, setAudience] = useState<Audience>("general_public");
  const [outputType, setOutputType] = useState<OutputType>("research_summary");
  const [maxPapers, setMaxPapers] = useState(10);
  const [touched, setTouched] = useState(false);

  const trimmed = question.trim();
  const problem =
    trimmed.length < MIN_LENGTH
      ? `Please enter a research question of at least ${MIN_LENGTH} characters.`
      : !/[A-Za-z]{3,}/.test(trimmed)
        ? "The question must contain words, not just numbers or symbols."
        : null;

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (problem || busy) return;
    onSubmit({ question: trimmed, audience, output_type: outputType, max_papers: maxPapers });
  };

  return (
    <form className="card form" onSubmit={handleSubmit} noValidate>
      <div className="field">
        <div className="field-head">
          <label htmlFor="question">Research question</label>
          {sampleQuestion && (
            <button type="button" className="link-button" onClick={() => setQuestion(sampleQuestion)} disabled={busy}>
              Use sample question
            </button>
          )}
        </div>
        <textarea
          id="question"
          rows={3}
          maxLength={MAX_LENGTH}
          value={question}
          disabled={busy}
          placeholder="e.g. Does regular physical activity reduce the risk of depression in adults?"
          aria-invalid={touched && problem ? true : undefined}
          aria-describedby="question-help"
          onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setQuestion(e.target.value)}
          onBlur={() => setTouched(true)}
        />
        <div id="question-help" className="field-foot">
          <span className={touched && problem ? "error-text" : "muted"} role={touched && problem ? "alert" : undefined}>
            {touched && problem ? problem : "Ask a specific, health-related question."}
          </span>
          <span className="muted">
            {question.length}/{MAX_LENGTH}
          </span>
        </div>
      </div>

      <div className="form-row">
        <div className="field">
          <label htmlFor="audience">Audience</label>
          <select id="audience" value={audience} disabled={busy} onChange={(e) => setAudience(e.target.value as Audience)}>
            {AUDIENCE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="output">Output type</label>
          <select id="output" value={outputType} disabled={busy} onChange={(e) => setOutputType(e.target.value as OutputType)}>
            {OUTPUT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="papers">Papers to retrieve</label>
          <select id="papers" value={maxPapers} disabled={busy} onChange={(e) => setMaxPapers(Number(e.target.value))}>
            {PAPER_COUNT_OPTIONS.map((n) => (
              <option key={n} value={n}>
                Up to {n}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="form-actions">
        <button type="submit" className="primary" disabled={busy}>
          {busy ? (
            <>
              <span className="spinner" aria-hidden="true" /> Research in progress...
            </>
          ) : (
            "Run research workflow"
          )}
        </button>
        <span className="muted small">Searches PubMed and Europe PMC. Typically 20-90 seconds.</span>
      </div>
    </form>
  );
}
