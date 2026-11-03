"""Shared agent pieces: the error type and the grounding rules every LLM prompt starts with."""
from __future__ import annotations

from ..schemas import Paper
from ..text_utils import shorten


class AgentError(Exception):
    """An agent could not do its job. The message is shown to the user, so keep it readable."""


GROUNDING_RULES = """You are one component of a public-health research tool. Strict rules:
- Use ONLY the numbered sources provided in the user message. They are real records retrieved from PubMed / Europe PMC.
- NEVER invent or recall studies, authors, journals, statistics, percentages, sample sizes, dates or URLs.
- Every factual statement must cite its source id in square brackets, e.g. [S1] or [S1, S3]. Use only the ids provided.
- Only state a number if it appears verbatim in the cited source's text.
- If the sources do not answer something, say the evidence is lacking instead of filling the gap.
- Do not give personal medical advice, diagnoses or treatment instructions.
- Reply with ONE valid JSON object and nothing else."""


def describe_papers(papers: list[Paper], abstract_chars: int = 1800) -> str:
    """Render papers as the numbered source list used inside prompts."""
    blocks = []
    for p in papers:
        header = f"[{p.ref_id}] {p.title} ({p.journal or 'journal not stated'}, {p.year or 'year not stated'})"
        design = f"Study design: {p.study_design}" + (" (inferred from text)" if p.design_inferred else "")
        abstract = shorten(p.abstract, abstract_chars) if p.has_abstract else "(no abstract available)"
        blocks.append(f"{header}\n{design}\nAbstract: {abstract}")
    return "\n\n".join(blocks)
