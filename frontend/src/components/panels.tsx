import { Badge, refTone, strengthTone, supportTone } from "./Badge";
import { CitedText, RichText } from "./CitedText";
import { REF_STATUS_LABEL, STRENGTH_LABEL, SUPPORT_LABEL } from "../lib/format";
import type { Paper, ResearchRun } from "../types";

type PaperMap = Map<string, Paper>;

function List({ items, empty }: { items: string[]; empty?: string }) {
  if (items.length === 0) return empty ? <p className="muted">{empty}</p> : null;
  return (
    <ul className="plain-list">
      {items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------------------------------------
export function OutputPanel({ run, papers }: { run: ResearchRun; papers: PaperMap }) {
  const output = run.output;
  if (!output || output.mode === "none" || !output.content) {
    return (
      <div className="notice notice-warn">
        <strong>No content was generated.</strong>
        <List items={output?.flags ?? []} empty="No finding passed citation verification, so nothing could be written safely." />
      </div>
    );
  }
  return (
    <div>
      <div className="panel-head">
        <h3 className="panel-title">{output.title}</h3>
        <Badge tone={output.mode === "llm" ? "info" : "neutral"} title="How the text was produced">
          {output.mode === "llm" ? "AI-written from verified findings" : "Template from verified abstracts"}
        </Badge>
      </div>
      {output.flags.length > 0 && (
        <div className="notice notice-warn" role="note">
          <strong>Flagged for review</strong>
          <List items={output.flags} />
        </div>
      )}
      <RichText content={output.content} papers={papers} />
      {output.cited_ref_ids.length > 0 && (
        <p className="small muted">
          Sources used:{" "}
          {output.cited_ref_ids.map((id) => {
            const paper = papers.get(id);
            return (
              <span key={id} className="chip">
                {paper?.url ? (
                  <a href={paper.url} target="_blank" rel="noopener noreferrer" title={paper.title}>
                    {id}
                  </a>
                ) : (
                  id
                )}
              </span>
            );
          })}
        </p>
      )}
      <p className="disclaimer">{output.disclaimer}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
export function EvidencePanel({ run, papers }: { run: ResearchRun; papers: PaperMap }) {
  const analysis = run.analysis;
  if (!analysis) return <p className="muted">The evidence analysis did not run.</p>;
  const claims = run.citations?.claims ?? [];
  return (
    <div>
      <div className="panel-head">
        <h3 className="panel-title">Evidence analysis</h3>
        <Badge tone={analysis.mode === "llm" ? "info" : "neutral"}>{analysis.mode === "llm" ? "AI synthesis" : "Extractive (no AI)"}</Badge>
      </div>
      {analysis.summary && (
        <p>
          <CitedText text={analysis.summary} papers={papers} />
        </p>
      )}

      {Object.keys(analysis.study_design_counts).length > 0 && (
        <p className="small">
          <span className="muted">Study designs retrieved: </span>
          {Object.entries(analysis.study_design_counts).map(([label, count]) => (
            <span key={label} className="chip">
              {count} x {label}
            </span>
          ))}
        </p>
      )}

      <h4>Findings</h4>
      {analysis.findings.length === 0 && <p className="muted">No findings could be extracted.</p>}
      <ul className="finding-list">
        {analysis.findings.map((finding, index) => {
          const check = claims[index];
          return (
            <li key={index} className="finding">
              <div className="finding-badges">
                <Badge tone={strengthTone(finding.strength)} title="Capped by study design; not a quality appraisal">
                  {STRENGTH_LABEL[finding.strength]}
                </Badge>
                {check && <Badge tone={supportTone(check.support)}>{SUPPORT_LABEL[check.support]}</Badge>}
              </div>
              <p>
                <CitedText text={finding.claim} papers={papers} />{" "}
                {finding.source_ids.length > 0 && !/\[S\d/.test(finding.claim) && <CitedText text={`[${finding.source_ids.join(", ")}]`} papers={papers} />}
              </p>
              {finding.caveat && <p className="small muted">Caveat: {finding.caveat}</p>}
              {check && check.issues.length > 0 && (
                <ul className="small issue-list">
                  {check.issues.map((issue, i) => (
                    <li key={i}>{issue}</li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>

      <h4>Evidence gaps</h4>
      <List items={analysis.evidence_gaps} empty="None identified." />
      <h4>Limitations</h4>
      <List items={analysis.limitations} empty="None identified." />
      {analysis.conflicting_evidence.length > 0 && (
        <>
          <h4>Conflicting evidence</h4>
          <List items={analysis.conflicting_evidence} />
        </>
      )}
      {analysis.notes.length > 0 && <List items={analysis.notes} />}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
export function VerificationPanel({ run }: { run: ResearchRun }) {
  const report = run.citations;
  if (!report) return <p className="muted">Citation verification did not run.</p>;
  const c = report.counts;
  const tiles: [string, number | undefined, string][] = [
    ["References verified", c.references_verified, "good"],
    ["Partly verified", c.references_partial, "warn"],
    ["References flagged", c.references_flagged, "bad"],
    ["Claims supported", c.claims_supported, "good"],
    ["Partly supported", c.claims_partial, "warn"],
    ["Claims unverified", c.claims_unsupported, "bad"],
  ];
  return (
    <div>
      <div className="panel-head">
        <h3 className="panel-title">Citation verification</h3>
        <Badge tone={report.llm_used ? "info" : "neutral"}>{report.llm_used ? "AI judge + code checks" : "Code checks only"}</Badge>
      </div>
      <div className="tiles">
        {tiles.map(([label, value, tone]) => (
          <div key={label} className={`tile tile-${tone}`}>
            <div className="tile-value">{value ?? 0}</div>
            <div className="tile-label">{label}</div>
          </div>
        ))}
      </div>

      {(report.flags.length > 0 || report.summary_issues.length > 0) && (
        <div className="notice notice-warn">
          <strong>Flags</strong>
          <List items={report.flags} />
        </div>
      )}
      {report.flags.length === 0 && <div className="notice notice-ok">No references or claims were flagged as unverifiable.</div>}

      <h4>Claims</h4>
      <ul className="finding-list">
        {report.claims.map((claim) => (
          <li key={claim.index} className="finding">
            <div className="finding-badges">
              <Badge tone={supportTone(claim.support)}>{SUPPORT_LABEL[claim.support]}</Badge>
              <span className="muted small">
                wording overlap {Math.round(claim.overlap * 100)}% - {claim.method === "llm+heuristic" ? "AI judge + code" : "code only"}
              </span>
            </div>
            <p>{claim.claim}</p>
            {claim.unverified_numbers.length > 0 && <p className="small error-text">Numbers not found in sources: {claim.unverified_numbers.join(", ")}</p>}
            {claim.issues.length > 0 && (
              <ul className="small issue-list">
                {claim.issues.map((issue, i) => (
                  <li key={i}>{issue}</li>
                ))}
              </ul>
            )}
            {claim.llm_reason && <p className="small muted">Judge: {claim.llm_reason}</p>}
          </li>
        ))}
        {report.claims.length === 0 && <p className="muted">There were no claims to check.</p>}
      </ul>

      <h4>References</h4>
      <ul className="ref-checks">
        {report.references.map((ref) => (
          <li key={ref.ref_id}>
            <details>
              <summary>
                <span className="ref-id">{ref.ref_id}</span>
                <span className="ref-title">{ref.title}</span>
                <Badge tone={refTone(ref.status)}>{REF_STATUS_LABEL[ref.status]}</Badge>
                {ref.cross_verified && <Badge tone="good" title="A second database returned the same record">Cross-checked</Badge>}
              </summary>
              <ul className="check-list">
                {ref.checks.map((check, i) => (
                  <li key={i} className={check.passed ? "check-pass" : `check-${check.severity}`}>
                    <span aria-hidden="true">{check.passed ? "✓" : check.severity === "error" ? "✕" : "!"}</span> {check.name}
                    {check.detail && <span className="muted"> - {check.detail}</span>}
                  </li>
                ))}
              </ul>
            </details>
          </li>
        ))}
      </ul>

      <h4>How verification works</h4>
      <p className="small muted">
        Each reference is checked for complete metadata, retractions and preprint status, and cross-checked against a second database. Each claim
        must cite a retrieved paper, share wording with its abstract, and every statistic must literally appear in the source. These checks catch
        invented sources and numbers; they cannot prove a claim is true. {report.notes.join(" ")}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
export function ReferencesPanel({ run }: { run: ResearchRun }) {
  const statusById = new Map((run.citations?.references ?? []).map((r) => [r.ref_id, r]));
  if (run.papers.length === 0) return <p className="muted">No papers were retrieved.</p>;
  return (
    <div>
      <div className="panel-head">
        <h3 className="panel-title">References ({run.papers.length})</h3>
      </div>
      {run.queries.length > 0 && (
        <p className="small muted">
          Search queries used: {run.queries.map((q) => (
            <code key={q} className="chip">
              {q}
            </code>
          ))}
        </p>
      )}
      <ul className="ref-list">
        {run.papers.map((paper) => {
          const check = statusById.get(paper.ref_id);
          return (
            <li key={paper.ref_id} id={`ref-${paper.ref_id}`} className="ref">
              <div className="ref-top">
                <span className="ref-id">{paper.ref_id}</span>
                <div>
                  <h4 className="ref-name">
                    {paper.url ? (
                      <a href={paper.url} target="_blank" rel="noopener noreferrer">
                        {paper.title}
                      </a>
                    ) : (
                      paper.title
                    )}
                  </h4>
                  <p className="small muted">
                    {paper.authors.slice(0, 4).join(", ")}
                    {paper.authors.length > 4 ? " et al." : ""}
                    {paper.authors.length > 0 ? " - " : ""}
                    {[paper.journal, paper.year].filter(Boolean).join(", ") || "Journal and year not available"}
                  </p>
                </div>
              </div>
              <div className="ref-badges">
                <Badge tone="neutral">{paper.study_design}</Badge>
                {check && <Badge tone={refTone(check.status)}>{REF_STATUS_LABEL[check.status]}</Badge>}
                {paper.is_retracted && <Badge tone="bad">Retracted</Badge>}
                {paper.is_preprint && <Badge tone="warn">Preprint - not peer reviewed</Badge>}
                {!paper.abstract && <Badge tone="warn">No abstract</Badge>}
                <span className="muted small">via {paper.sources.join(" + ")}</span>
              </div>
              <div className="ref-links">
                {paper.links.map((link) => (
                  <a key={link.url} href={link.url} target="_blank" rel="noopener noreferrer">
                    {link.label} {"↗"}
                  </a>
                ))}
                {paper.pmid && <span className="muted small">PMID {paper.pmid}</span>}
                {paper.doi && <span className="muted small">DOI {paper.doi}</span>}
              </div>
              {paper.metadata_notes.length > 0 && <p className="small error-text">{paper.metadata_notes.join(" ")}</p>}
              {paper.abstract && (
                <details>
                  <summary className="small">Abstract</summary>
                  <p className="small abstract">{paper.abstract}</p>
                </details>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
