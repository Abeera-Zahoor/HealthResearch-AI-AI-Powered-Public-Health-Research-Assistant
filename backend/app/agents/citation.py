"""Agent 3 - Citation Verification Agent.

Two independent layers:
  1. Reference checks: is each paper's metadata complete and plausible, is it retracted or a preprint,
     and does a second database independently return the same record (cross-verification)?
  2. Claim checks: does each finding cite real, retrieved papers, and do the cited abstracts actually
     contain its wording and numbers? If an LLM is enabled it also acts as a judge, but it must supply a
     VERBATIM quote that this code then looks for in the abstract - a made-up quote is rejected.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from ..apis import EuropePMCClient, PubMedClient, SourceError
from ..llm import LLMClient, LLMError
from ..paper_utils import is_valid_doi
from ..schemas import (
    CitationReport,
    ClaimVerification,
    EvidenceAnalysis,
    MetadataCheck,
    Paper,
    ReferenceVerification,
)
from ..verification import check_claim, find_text_problems, papers_text, quote_in_text
from .base import describe_papers
from .research import titles_match

JUDGE_SYSTEM = """You are a strict fact-checking assistant. For each claim, decide whether the cited source texts support it.
Rules:
- Judge ONLY from the source text provided. Do not use outside knowledge.
- "supported" = the source states this; "partial" = only part of it, or it overstates (e.g. causal wording from observational data);
  "unsupported" = the source does not say this.
- For "supported" and "partial" you MUST copy ONE exact, word-for-word passage from the source's title or abstract into "quote".
  If you cannot find such a passage, the verdict must be "unsupported" with an empty quote.
Reply with ONE JSON object:
{"judgements": [{"claim_index": 1, "verdict": "supported|partial|unsupported", "source_id": "S1", "quote": "...", "reason": "one short sentence"}]}"""

SEVERITY_PENALTY = {"supported": 0, "partial": 1, "unsupported": 2}
BY_PENALTY = {0: "supported", 1: "partial", 2: "unsupported"}


class CitationVerificationAgent:
    key = "verification"
    name = "Citation Verification Agent"

    def __init__(
        self,
        pubmed: Optional[PubMedClient] = None,
        europepmc: Optional[EuropePMCClient] = None,
        llm: Optional[LLMClient] = None,
    ) -> None:
        self.pubmed = pubmed
        self.europepmc = europepmc
        self.llm = llm

    # ------------------------------------------------------------------
    def run(self, papers: list[Paper], analysis: EvidenceAnalysis) -> CitationReport:
        report = CitationReport()
        by_id = {p.ref_id: p for p in papers}
        report.references = [self.verify_reference(p) for p in papers]

        report.claims = [
            check_claim(i, f.claim, f.source_ids, by_id) for i, f in enumerate(analysis.findings, start=1)
        ]
        if self.llm is not None and self.llm.enabled and report.claims:
            self._apply_llm_judge(report, by_id)
        elif report.claims:
            report.notes.append(
                "Claim checks used wording/number matching only (no LLM judge). "
                "They catch missing sources and unsupported numbers but cannot judge meaning."
            )

        if analysis.mode == "llm" and analysis.summary:
            allowed = papers_text(p for p in papers if p.has_abstract)
            report.summary_issues = find_text_problems(analysis.summary, by_id, allowed)
        self._finish(report)
        return report

    # ------------------------------------------------------------------
    def verify_reference(self, paper: Paper) -> ReferenceVerification:
        checks: list[MetadataCheck] = []

        def add(name: str, passed: bool, severity: str, detail: str = "") -> None:
            checks.append(MetadataCheck(name=name, passed=passed, severity="info" if passed else severity, detail=detail))  # type: ignore[arg-type]

        add("Title present", bool(paper.title.strip()), "error")
        has_id = bool(paper.pmid or is_valid_doi(paper.doi))
        add("Stable identifier (PMID or DOI)", has_id, "error", "" if has_id else "No PMID or valid DOI, so the record cannot be traced.")
        if paper.doi:
            add("DOI format valid", is_valid_doi(paper.doi), "warning", paper.doi)
        year_ok = paper.year is not None and 1900 <= paper.year <= datetime.now().year + 1
        add("Publication year plausible", year_ok, "warning", str(paper.year or "missing"))
        add("Journal named", bool(paper.journal), "warning")
        add("Abstract available", paper.has_abstract, "warning", "" if paper.has_abstract else "Claims cannot be checked against this paper.")
        add("Not retracted", not (paper.is_retracted or paper.is_retraction_notice), "error", "Marked as retracted in the database." if paper.is_retracted else "")
        add("Peer reviewed (not a preprint)", not paper.is_preprint, "warning", "Preprints have not been peer reviewed." if paper.is_preprint else "")
        for note in paper.metadata_notes:
            add("Records agree", False, "error", note)

        cross_verified = self._cross_check(paper, add)
        errors = any(c.severity == "error" and not c.passed for c in checks)
        warnings = any(c.severity == "warning" and not c.passed for c in checks)
        status = "flagged" if errors else ("verified" if cross_verified and not warnings else "partial")
        return ReferenceVerification(
            ref_id=paper.ref_id, title=paper.title, status=status, cross_verified=cross_verified, checks=checks  # type: ignore[arg-type]
        )

    def _cross_check(self, paper: Paper, add) -> bool:
        if paper.metadata_notes:
            return False
        databases = set(paper.sources)
        if {"PubMed", "Europe PMC"} <= databases:
            add("Cross-database match", True, "info", "PubMed and Europe PMC both returned this record with matching titles.")
            return True
        try:
            other_title: Optional[str] = None
            if databases == {"PubMed"} and paper.pmid and self.europepmc is not None:
                found = self.europepmc.lookup(pmid=paper.pmid)
                other_title, other = (found.title if found else None), "Europe PMC"
            elif databases == {"Europe PMC"} and paper.pmid and self.pubmed is not None:
                found_list = self.pubmed.fetch([paper.pmid])
                other_title, other = (found_list[0].title if found_list else None), "PubMed"
            else:
                add("Cross-database match", False, "warning", "Only one database returned this record and it has no PMID to look up elsewhere.")
                return False
        except SourceError as exc:
            add("Cross-database match", False, "warning", f"Could not cross-check: {exc}")
            return False
        if other_title is None:
            add("Cross-database match", False, "error", f"{other} has no record for PMID {paper.pmid}.")
            return False
        if not titles_match(paper.title, other_title):
            add("Cross-database match", False, "error", f"Title in {other} differs: “{other_title}”.")
            return False
        add("Cross-database match", True, "info", f"{other} independently returned the same title for PMID {paper.pmid}.")
        return True

    # ------------------------------------------------------------------
    def _apply_llm_judge(self, report: CitationReport, by_id: dict[str, Paper]) -> None:
        assert self.llm is not None
        cited_ids = list(dict.fromkeys(i for c in report.claims for i in c.source_ids if i in by_id))
        sources = describe_papers([by_id[i] for i in cited_ids], abstract_chars=3000)
        claims = "\n".join(f"{c.index}. {c.claim} (cites: {', '.join(c.source_ids) or 'nothing'})" for c in report.claims)
        try:
            data = self.llm.complete_json(JUDGE_SYSTEM, f"Sources:\n\n{sources}\n\nClaims:\n{claims}")
        except LLMError as exc:
            report.notes.append(f"The LLM judge failed ({exc}); wording/number matching only was used.")
            return
        report.llm_used = True
        verdicts = {}
        for item in data.get("judgements", []) or []:
            if isinstance(item, dict) and str(item.get("claim_index", "")).isdigit():
                verdicts[int(item["claim_index"])] = item

        for claim in report.claims:
            item = verdicts.get(claim.index)
            claim.method = "llm+heuristic"
            if item is None:
                claim.issues.append("The LLM judge gave no verdict for this claim.")
                claim.support = self._worse(claim.support, "partial")
                continue
            verdict = str(item.get("verdict", "unsupported")).lower()
            verdict = verdict if verdict in SEVERITY_PENALTY else "unsupported"
            quote = str(item.get("quote", "")).strip()
            reason = str(item.get("reason", "")).strip()
            if verdict != "unsupported":
                source = by_id.get(str(item.get("source_id", "")).strip().upper())
                haystack = papers_text([source]) if source else papers_text(by_id[i] for i in claim.source_ids if i in by_id)
                if not quote or not quote_in_text(quote, haystack):
                    claim.issues.append("The LLM judge's supporting quote was not found in the source text, so its verdict was not trusted.")
                    verdict = "unsupported"
                    quote = ""
            claim.llm_reason = f"{reason} Quote: “{quote}”" if quote else reason
            if verdict != "supported" and not any("judge" in i for i in claim.issues):
                claim.issues.append(f"The LLM judge rated this claim '{verdict}'" + (f": {reason}" if reason else "."))
            claim.support = self._worse(claim.support, verdict)

    @staticmethod
    def _worse(a: str, b: str) -> str:
        return BY_PENALTY[max(SEVERITY_PENALTY[a], SEVERITY_PENALTY[b])]

    @staticmethod
    def _finish(report: CitationReport) -> None:
        refs, claims = report.references, report.claims
        report.counts = {
            "references_total": len(refs),
            "references_verified": sum(r.status == "verified" for r in refs),
            "references_partial": sum(r.status == "partial" for r in refs),
            "references_flagged": sum(r.status == "flagged" for r in refs),
            "claims_total": len(claims),
            "claims_supported": sum(c.support == "supported" for c in claims),
            "claims_partial": sum(c.support == "partial" for c in claims),
            "claims_unsupported": sum(c.support == "unsupported" for c in claims),
        }
        for ref in refs:
            for check in ref.checks:
                if check.severity == "error" and not check.passed:
                    report.flags.append(f"{ref.ref_id}: {check.name} - {check.detail or 'failed'}")
        for claim in claims:
            if claim.support == "unsupported":
                report.flags.append(f"Claim {claim.index} could not be verified and will not be used: {'; '.join(claim.issues) or 'no support found'}")
        for issue in report.summary_issues:
            report.flags.append(f"Analysis summary: {issue}")
