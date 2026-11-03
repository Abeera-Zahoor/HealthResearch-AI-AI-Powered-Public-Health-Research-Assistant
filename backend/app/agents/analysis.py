"""Agent 2 - Evidence Analysis Agent: summarises findings, evidence gaps and limitations.

With an LLM it synthesises the retrieved abstracts. Without one it runs in "extractive" mode:
findings are the authors' own conclusion sentences copied verbatim from each abstract.
Gaps and limitations that can be computed from the data (study designs, missing abstracts,
preprints...) are always computed in code, so they never depend on the model.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Optional

from ..llm import LLMClient, LLMError
from ..schemas import EvidenceAnalysis, Finding, Paper, Strength
from ..text_utils import extract_citation_ids, shorten, split_sentences
from .base import GROUNDING_RULES, describe_papers

MAX_EXTRACTIVE_FINDINGS = 8
STRENGTH_ORDER = {"limited": 0, "moderate": 1, "strong": 2}

ANALYSIS_SYSTEM = (
    GROUNDING_RULES
    + """

Your job: analyse the evidence for the research question.
JSON schema:
{
  "summary": "3-5 sentences synthesising what the sources found, with [S#] citations",
  "findings": [
    {"claim": "one specific finding, close to the abstract's wording, with [S#]",
     "source_ids": ["S1"], "strength": "strong|moderate|limited",
     "caveat": "important limitation of this finding (design, population, size, short follow-up...)"}
  ],
  "evidence_gaps": ["what the retrieved sources do NOT show"],
  "limitations": ["limitations of the available evidence"],
  "conflicting_evidence": ["places where sources disagree, with [S#]; empty list if none"]
}
Give 3-8 findings. Prefer the highest-quality study designs. Do not claim causation from observational designs."""
)

_LABEL_RE = re.compile(r"(?:^|\s)([A-Z][A-Z /&-]{3,}):\s")
_CONCLUSION_LABELS = ("CONCLUSIONS", "CONCLUSION", "INTERPRETATION", "FINDINGS", "RESULTS", "RESULT")


def strength_ceiling(papers: list[Paper]) -> Strength:
    """The strongest label the cited study designs can justify (a rough screening rule, not an appraisal)."""
    best = max((p.evidence_rank for p in papers), default=0)
    if best >= 7:
        return "strong"
    if best >= 5:
        return "moderate"
    return "limited"


def key_sentence(abstract: str) -> str:
    """The authors' conclusion (or results) sentence, copied verbatim from the abstract."""
    text = " ".join(abstract.split())
    labels = list(_LABEL_RE.finditer(text))
    for wanted in _CONCLUSION_LABELS:
        for position, match in enumerate(labels):
            if match.group(1).strip() == wanted:
                end = labels[position + 1].start() if position + 1 < len(labels) else len(text)
                section = text[match.end() : end].strip()
                sentences = split_sentences(section)
                if sentences:
                    first = sentences[0]
                    if len(first) < 40 and len(sentences) > 1:
                        first = f"{first} {sentences[1]}"
                    return shorten(first, 400)
    sentences = split_sentences(text)
    return shorten(sentences[-1], 400) if sentences else ""


class EvidenceAnalysisAgent:
    key = "analysis"
    name = "Evidence Analysis Agent"

    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self.llm = llm

    # ------------------------------------------------------------------
    @staticmethod
    def eligible(papers: list[Paper]) -> list[Paper]:
        return [p for p in papers if p.has_abstract and not p.is_retracted and not p.is_retraction_notice]

    def run(self, question: str, papers: list[Paper]) -> EvidenceAnalysis:
        usable = self.eligible(papers)
        analysis = EvidenceAnalysis(study_design_counts=dict(Counter(p.study_design for p in papers)))
        gaps, limits = self.computed_gaps_and_limitations(papers, usable)

        if not usable:
            analysis.summary = "None of the retrieved papers has an abstract that can be analysed."
            analysis.evidence_gaps = gaps
            analysis.limitations = limits
            analysis.notes.append("No findings were generated because there is no abstract text to analyse.")
            return analysis

        if self.llm is not None and self.llm.enabled:
            try:
                self._run_llm(question, papers, usable, analysis)
            except LLMError as exc:
                analysis = EvidenceAnalysis(study_design_counts=analysis.study_design_counts)
                analysis.notes.append(f"The LLM step failed ({exc}); extractive mode was used instead.")
                self._run_extractive(usable, analysis)
        else:
            self._run_extractive(usable, analysis)

        analysis.evidence_gaps = list(dict.fromkeys([*gaps, *analysis.evidence_gaps]))
        analysis.limitations = list(dict.fromkeys([*limits, *analysis.limitations]))
        return analysis

    # ------------------------------------------------------------------
    @staticmethod
    def computed_gaps_and_limitations(papers: list[Paper], usable: list[Paper]) -> tuple[list[str], list[str]]:
        gaps: list[str] = []
        limits = [
            "Only titles and abstracts were analysed, not full texts, so details in the full papers may be missed.",
            "This is a rapid literature search of PubMed and Europe PMC, not a systematic review; relevant studies may be missing.",
        ]
        if len(usable) < 5:
            gaps.append(f"Only {len(usable)} paper(s) with an abstract were available, which is a thin evidence base.")
        top_rank = max((p.evidence_rank for p in usable), default=0)
        if top_rank < 6:
            gaps.append("No randomized controlled trials or systematic reviews were found among the retrieved papers, so causal conclusions are not supported.")
        elif top_rank < 7:
            gaps.append("No systematic reviews or meta-analyses were found among the retrieved papers.")
        no_abstract = [p.ref_id for p in papers if not p.has_abstract]
        if no_abstract:
            limits.append(f"{len(no_abstract)} paper(s) have no abstract and were not analysed: {', '.join(no_abstract)}.")
        preprints = [p.ref_id for p in papers if p.is_preprint]
        if preprints:
            limits.append(f"Preprints (not peer reviewed) are included: {', '.join(preprints)}.")
        retracted = [p.ref_id for p in papers if p.is_retracted]
        if retracted:
            limits.append(f"Retracted paper(s) were excluded from the analysis: {', '.join(retracted)}.")
        inferred = [p.ref_id for p in usable if p.design_inferred]
        if inferred:
            limits.append(f"Study design was inferred from the text (not from database labels) for: {', '.join(inferred)}.")
        return gaps, limits

    def _run_extractive(self, usable: list[Paper], analysis: EvidenceAnalysis) -> None:
        analysis.mode = "extractive"
        for paper in usable[:MAX_EXTRACTIVE_FINDINGS]:
            sentence = key_sentence(paper.abstract)
            if not sentence:
                continue
            analysis.findings.append(
                Finding(
                    claim=sentence,
                    source_ids=[paper.ref_id],
                    strength=strength_ceiling([paper]),
                    caveat=f"{paper.study_design}; authors' own statement from the abstract, not independently appraised.",
                )
            )
        designs = Counter(p.study_design for p in usable)
        mix = ", ".join(f"{n} {label.lower()}" for label, n in designs.most_common())
        analysis.summary = (
            f"Extractive mode (no LLM): {len(analysis.findings)} finding(s) were taken word-for-word from the abstracts of "
            f"{len(usable)} retrieved paper(s) ({mix}). No synthesis across studies was attempted."
        )
        analysis.notes.append(
            "Extractive mode cannot compare studies or detect conflicting results. Add an LLM provider in backend/.env for a synthesis."
        )

    def _run_llm(self, question: str, papers: list[Paper], usable: list[Paper], analysis: EvidenceAnalysis) -> None:
        assert self.llm is not None
        user = f"Research question: {question}\n\nSources:\n\n{describe_papers(usable)}"
        data = self.llm.complete_json(ANALYSIS_SYSTEM, user)
        by_id = {p.ref_id: p for p in papers}

        for raw in data.get("findings", []) or []:
            if not isinstance(raw, dict) or not str(raw.get("claim", "")).strip():
                continue
            claim = str(raw["claim"]).strip()
            ids = [str(i).strip().upper() for i in raw.get("source_ids", []) or []]
            ids = list(dict.fromkeys([*ids, *extract_citation_ids(claim)]))
            cited = [by_id[i] for i in ids if i in by_id]
            wanted = str(raw.get("strength", "limited")).lower()
            wanted = wanted if wanted in STRENGTH_ORDER else "limited"
            ceiling = strength_ceiling(cited)
            strength = wanted if STRENGTH_ORDER[wanted] <= STRENGTH_ORDER[ceiling] else ceiling
            analysis.findings.append(
                Finding(claim=claim, source_ids=ids, strength=strength, caveat=str(raw.get("caveat", "")).strip())  # type: ignore[arg-type]
            )
        if not analysis.findings:
            raise LLMError("The model returned no usable findings.")

        analysis.mode = "llm"
        analysis.summary = str(data.get("summary", "")).strip()
        for field_name in ("evidence_gaps", "limitations", "conflicting_evidence"):
            values = data.get(field_name, []) or []
            setattr(analysis, field_name, [str(v).strip() for v in values if str(v).strip()])
        analysis.notes.append(
            "Finding strength was capped by study design (only systematic reviews/meta-analyses can be 'strong'; "
            "only randomized trials, guidelines or better can be 'moderate')."
        )
