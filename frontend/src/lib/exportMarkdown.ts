import type { ResearchRun } from "../types";
import { audienceLabel, outputLabel } from "./format";

/** Builds a self-contained Markdown report (content, flags, verification summary and reference list). */
export function runToMarkdown(run: ResearchRun): string {
  const lines: string[] = [];
  lines.push(`# ${run.output?.title || "HealthResearch AI report"}`, "");
  lines.push(`**Research question:** ${run.question}`);
  lines.push(`**Audience:** ${audienceLabel(run.audience)} | **Format:** ${outputLabel(run.output_type)}`);
  lines.push(`**Generated:** ${run.created_at}`, "");

  if (run.output?.content) {
    lines.push(run.output.content, "");
    if (run.output.flags.length) {
      lines.push("## Flagged for review", ...run.output.flags.map((f) => `- ${f}`), "");
    }
  } else {
    lines.push("_No content was generated for this run._", "");
  }

  if (run.analysis) {
    if (run.analysis.evidence_gaps.length) lines.push("## Evidence gaps", ...run.analysis.evidence_gaps.map((g) => `- ${g}`), "");
    if (run.analysis.limitations.length) lines.push("## Limitations", ...run.analysis.limitations.map((l) => `- ${l}`), "");
  }

  const counts = run.citations?.counts;
  if (counts) {
    lines.push(
      "## Verification summary",
      `- References: ${counts.references_verified ?? 0} verified, ${counts.references_partial ?? 0} partly verified, ${counts.references_flagged ?? 0} flagged`,
      `- Claims: ${counts.claims_supported ?? 0} supported, ${counts.claims_partial ?? 0} partly supported, ${counts.claims_unsupported ?? 0} unverified`,
      "",
    );
  }

  lines.push("## References");
  if (run.papers.length === 0) lines.push("_No papers retrieved._");
  for (const paper of run.papers) {
    const authors = paper.authors.length > 3 ? `${paper.authors.slice(0, 3).join(", ")} et al.` : paper.authors.join(", ");
    const venue = [paper.journal, paper.year].filter(Boolean).join(", ");
    const link = paper.url ? ` ${paper.url}` : "";
    lines.push(`- [${paper.ref_id}] ${authors ? authors.replace(/\.$/, "") + ". " : ""}${paper.title}. ${venue}.${link}`);
  }
  lines.push("");
  if (run.output?.disclaimer) lines.push(`> ${run.output.disclaimer}`);
  return lines.join("\n");
}

export function downloadText(filename: string, text: string): void {
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
