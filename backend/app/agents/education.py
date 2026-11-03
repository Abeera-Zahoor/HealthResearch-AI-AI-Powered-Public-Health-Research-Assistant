"""Agent 4 - Health Education Agent: turns the VERIFIED findings into audience-ready content.

Only findings that passed verification are used. Generated text is checked again afterwards:
unknown citation markers are removed and any statistic that is not in the verified sources is flagged.
Without an LLM it assembles the output from templates using the verified sentences word for word.
"""
from __future__ import annotations

from typing import Optional

from ..llm import LLMClient, LLMError
from ..schemas import (
    AUDIENCE_LABELS,
    Audience,
    CitationReport,
    EducationOutput,
    EvidenceAnalysis,
    OUTPUT_LABELS,
    OutputType,
    Paper,
)
from ..text_utils import extract_citation_ids, shorten
from ..verification import find_text_problems, papers_text, sanitize_citations
from .base import GROUNDING_RULES, describe_papers

DISCLAIMER = (
    "Educational summary of published research, not medical advice. Check every statement against the linked "
    "sources before sharing, and speak to a qualified health professional about personal health decisions."
)

AUDIENCE_STYLE = {
    Audience.general_public: "Plain language at about a grade-8 reading level, short sentences, explain any technical term.",
    Audience.patients: "Warm, plain language for patients and caregivers; no jargon; say what is and is not known; never give treatment instructions.",
    Audience.clinicians: "Concise and clinical; name study designs and certainty; no patient-specific advice.",
    Audience.policymakers: "Brief and decision-oriented: what the evidence shows, how certain it is, what is missing for decisions.",
    Audience.students: "Educational and clear; explain study designs and why certainty differs.",
    Audience.journalists: "Accurate and quotable; stress certainty levels and what must not be overstated; avoid hype.",
}

FORMAT_GUIDE = {
    OutputType.research_summary: (
        "A research summary of 250-400 words with the markdown headings: '## Key findings' (bullets), "
        "'## How strong is the evidence?', '## Gaps and limitations', '## Bottom line'."
    ),
    OutputType.public_health_article: (
        "A public health article of 450-650 words: a short engaging intro, 3-4 sections with '## ' headings, and a "
        "closing section '## What we still don't know'. Factual tone, no sensationalism, no calls to take medical action."
    ),
    OutputType.social_media_posts: (
        "Four social media posts, each introduced by a heading line: '### X (max 280 characters)', '### LinkedIn', "
        "'### Facebook', '### Instagram'. Each post states one or two verified findings with [S#] citations, stays honest about "
        "uncertainty, and ends with 2-3 hashtags. No emojis that imply certainty or alarm."
    ),
    OutputType.video_script: (
        "A 60-90 second educational video script. Use blocks like '### Scene 1 (0:00-0:10)' followed by lines starting "
        "'Visual:' and 'Narration:'. Cover a hook, 2-3 verified findings, what is still unknown, and a closing line that points "
        "viewers to the sources. Do not show statistics on screen unless they are in the verified findings."
    ),
}

EDUCATION_SYSTEM = (
    GROUNDING_RULES
    + """

You write health education content using ONLY the verified findings given. Do not add facts from memory.
Reply with JSON: {"title": "short title", "content": "the full text, markdown allowed, with [S#] citations"}."""
)


class HealthEducationAgent:
    key = "education"
    name = "Health Education Agent"

    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self.llm = llm

    # ------------------------------------------------------------------
    def run(
        self,
        question: str,
        audience: Audience,
        output_type: OutputType,
        papers: list[Paper],
        analysis: EvidenceAnalysis,
        citations: CitationReport,
    ) -> EducationOutput:
        by_id = {p.ref_id: p for p in papers}
        approved = [
            (finding, check)
            for finding, check in zip(analysis.findings, citations.claims)
            if check.support in ("supported", "partial")
        ]
        output = EducationOutput(disclaimer=DISCLAIMER)
        if not approved:
            output.flags.append(
                "No finding passed citation verification, so no content was generated. This prevents unverified claims from being published."
            )
            return output

        approved_ids = list(dict.fromkeys(i for finding, _ in approved for i in finding.source_ids if i in by_id))
        if self.llm is not None and self.llm.enabled:
            try:
                self._run_llm(question, audience, output_type, approved, approved_ids, by_id, analysis, output)
            except LLMError as exc:
                output.flags.append(f"The LLM step failed ({exc}); a template was used instead.")
                output.title = output.content = ""
        if not output.content:
            self._run_template(question, output_type, approved, approved_ids, by_id, analysis, output)

        valid_ids = set(by_id)
        output.content = sanitize_citations(output.content, valid_ids)
        allowed_text = papers_text(by_id[i] for i in approved_ids) + "\n" + "\n".join(f.claim for f, _ in approved)
        if output.mode == "llm":
            output.flags.extend(find_text_problems(output.content, by_id, allowed_text))
        cited = list(dict.fromkeys(extract_citation_ids(output.content)))
        output.cited_ref_ids = [i for i in cited if i in by_id]
        stray = [i for i in output.cited_ref_ids if i not in approved_ids]
        if stray:
            output.flags.append(f"The text cites {', '.join(stray)}, which no verified finding relies on. Check those statements.")
        if output.mode == "llm" and not output.cited_ref_ids:
            output.flags.append("The generated text contains no source citations; treat every statement as unverified.")
        partial = [c.index for _, c in approved if c.support == "partial"]
        if partial:
            output.flags.append(
                f"Finding(s) {', '.join(map(str, partial))} were only partially supported by their sources; wording should be treated with extra caution."
            )
        return output

    # ------------------------------------------------------------------
    def _run_llm(self, question, audience, output_type, approved, approved_ids, by_id, analysis, output) -> None:
        findings = "\n".join(
            f"- {f.claim} (sources: {', '.join(f.source_ids)}; evidence: {f.strength}; "
            f"verification: {c.support}{'; caveat: ' + f.caveat if f.caveat else ''})"
            for f, c in approved
        )
        sources = describe_papers([by_id[i] for i in approved_ids], abstract_chars=600)
        gaps = "\n".join(f"- {g}" for g in [*analysis.evidence_gaps, *analysis.limitations][:8])
        user = (
            f"Research question: {question}\n"
            f"Audience: {AUDIENCE_LABELS[audience]}. Style: {AUDIENCE_STYLE[audience]}\n"
            f"Format: {FORMAT_GUIDE[output_type]}\n\n"
            f"VERIFIED FINDINGS (the only facts you may use):\n{findings}\n\n"
            f"EVIDENCE GAPS AND LIMITATIONS (mention the important ones):\n{gaps}\n\n"
            f"Source records for reference:\n{sources}"
        )
        data = self.llm.complete_json(EDUCATION_SYSTEM, user, max_tokens=None)  # type: ignore[union-attr]
        content = str(data.get("content", "")).strip()
        if not content:
            raise LLMError("The model returned no content.")
        output.mode = "llm"
        output.title = str(data.get("title", "")).strip() or OUTPUT_LABELS[output_type]
        output.content = content

    def _run_template(self, question, output_type, approved, approved_ids, by_id, analysis, output) -> None:
        output.mode = "template"
        cites = lambda f: "[" + ", ".join(f.source_ids) + "]"  # noqa: E731
        bullets = "\n".join(f"- {f.claim} {cites(f)} ({f.strength} evidence)" for f, _ in approved)
        gaps = "\n".join(f"- {g}" for g in [*analysis.evidence_gaps, *analysis.limitations][:5]) or "- Not assessed."
        n = len(approved_ids)
        bottom = (
            f"This summary is based on {n} retrieved paper(s). Findings come from study abstracts and have not been "
            "independently appraised; the evidence should be read as limited unless a strong study design is noted."
        )

        if output_type == OutputType.research_summary:
            output.title = "Research summary"
            output.content = (
                f"## Key findings\n{bullets}\n\n## How strong is the evidence?\n{analysis.summary}\n\n"
                f"## Gaps and limitations\n{gaps}\n\n## Bottom line\n{bottom}"
            )
        elif output_type == OutputType.public_health_article:
            output.title = f"What does the research say? {shorten(question, 90)}"
            output.content = (
                f"People often ask: {question}\n\nThis article summarises what published studies say. "
                f"It draws on {n} paper(s) found in PubMed and Europe PMC.\n\n"
                f"## What the studies report\n{bullets}\n\n## How much can we trust this?\n{analysis.summary}\n\n"
                f"## What we still don't know\n{gaps}\n\n{bottom}"
            )
        elif output_type == OutputType.social_media_posts:
            output.title = "Social media posts"
            short = [(f, c) for f, c in approved if len(f.claim) <= 190][:3] or approved[:1]
            posts = []
            for label, (f, _) in zip(("X", "LinkedIn", "Facebook"), short):
                posts.append(f"### {label}\nResearch note: {shorten(f.claim, 190)} {cites(f)} (limited, abstract-level evidence) #PublicHealth #Research")
            posts.append("### Instagram\nWhat does research say? Swipe through the sources, and remember: abstracts are not the whole story. #PublicHealth #ScienceCommunication")
            output.content = "\n\n".join(posts)
        else:
            output.title = "Short video script"
            scenes = [
                "### Scene 1 (0:00-0:10)\nVisual: Title card with the research question.\n"
                f"Narration: {shorten(question, 140)} Here is what published studies say."
            ]
            for number, (f, _) in enumerate(approved[:3], start=2):
                scenes.append(f"### Scene {number}\nVisual: Text card quoting the source.\nNarration: {f.claim} {cites(f)}")
            scenes.append(
                f"### Scene {len(scenes) + 1}\nVisual: Source list on screen.\n"
                "Narration: This evidence is limited. Check the linked sources, and talk to a health professional about personal decisions."
            )
            output.content = "\n\n".join(scenes)
        output.flags.append(
            "Template mode (no LLM): wording is copied from study abstracts and is not adapted to the audience. "
            "Set up an LLM provider in backend/.env for audience-tailored writing."
        )
