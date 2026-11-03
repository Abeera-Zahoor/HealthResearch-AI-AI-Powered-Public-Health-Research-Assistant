"""Deterministic claim and text checks shared by the Citation Verification and Education agents.

Nothing here calls an LLM, so it cannot be talked into approving something false.
The checks are conservative heuristics:
  * every cited source id must exist in the retrieved paper list,
  * the cited papers must have an abstract to check against,
  * the claim must share vocabulary with its sources,
  * every statistic in the claim (45%, 2.3, 120...) must literally appear in the sources.
They do NOT prove a claim is true - they catch the most common ways generated text drifts from sources.
"""
from __future__ import annotations

import re
from typing import Iterable

from .schemas import ClaimVerification, Paper
from .text_utils import (
    CITE_RE,
    all_numbers,
    extract_citation_ids,
    find_statistics,
    lexical_overlap,
    shorten,
    split_sentences,
    strip_citations,
    strip_nonclaim_numbers,
)

OVERLAP_UNSUPPORTED = 0.25
OVERLAP_PARTIAL = 0.5
UNVERIFIED_MARK = "[unverified source]"


def papers_text(papers: Iterable[Paper]) -> str:
    return "\n".join(f"{p.title}\n{p.abstract}\n{p.year or ''}" for p in papers)


def unverified_statistics(text: str, source_text: str) -> list[str]:
    """Statistics in `text` that do not appear anywhere in `source_text`."""
    claimed = find_statistics(strip_nonclaim_numbers(strip_citations(text)))
    return sorted(claimed - all_numbers(source_text), key=lambda n: (len(n), n))


def normalise_for_quote(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-")
    return " ".join(text.lower().split())


def quote_in_text(quote: str, text: str) -> bool:
    """True if every fragment of `quote` (split on '...') is found verbatim in `text`."""
    haystack = normalise_for_quote(text)
    fragments = [f.strip(" .\"'") for f in re.split(r"\.\.\.|…", quote)]
    fragments = [normalise_for_quote(f) for f in fragments if len(f.strip()) >= 12]
    return bool(fragments) and all(f in haystack for f in fragments)


def check_claim(index: int, claim: str, source_ids: list[str], papers_by_id: dict[str, Paper]) -> ClaimVerification:
    """Heuristic check of one claim against the papers it cites."""
    ids = list(dict.fromkeys(source_ids))
    valid = [papers_by_id[i] for i in ids if i in papers_by_id]
    unknown = [i for i in ids if i not in papers_by_id]
    issues: list[str] = []

    if not ids:
        issues.append("The claim cites no source.")
    if unknown:
        issues.append(f"Cites reference(s) that do not exist in the retrieved list: {', '.join(unknown)}.")
    retracted = [p.ref_id for p in valid if p.is_retracted or p.is_retraction_notice]
    if retracted:
        issues.append(f"Cites retracted or retraction-notice paper(s): {', '.join(retracted)}.")

    with_abstract = [p for p in valid if p.has_abstract]
    if valid and not with_abstract:
        issues.append("None of the cited papers has an abstract, so the claim cannot be checked against its source.")

    source_text = papers_text(with_abstract)
    overlap = round(lexical_overlap(strip_citations(claim), source_text), 2) if with_abstract else 0.0
    numbers = unverified_statistics(claim, papers_text(valid)) if valid else []
    if numbers:
        issues.append(f"Number(s) not found in the cited abstract(s): {', '.join(numbers)}.")

    if not valid or retracted or not with_abstract:
        support = "unsupported"
    elif overlap < OVERLAP_UNSUPPORTED:
        support = "unsupported"
        issues.append(f"Very little of the claim's wording appears in the cited abstract(s) (overlap {overlap:.0%}).")
    elif overlap < OVERLAP_PARTIAL or numbers or unknown:
        support = "partial"
        if overlap < OVERLAP_PARTIAL:
            issues.append(f"Only part of the claim's wording appears in the cited abstract(s) (overlap {overlap:.0%}).")
    else:
        support = "supported"

    return ClaimVerification(
        index=index,
        claim=claim,
        source_ids=ids,
        support=support,
        overlap=overlap,
        unverified_numbers=numbers,
        issues=issues,
    )


def find_text_problems(text: str, papers_by_id: dict[str, Paper], allowed_source_text: str) -> list[str]:
    """Sentence-level problems in free text: unknown citations and statistics that no source contains."""
    problems: list[str] = []
    for sentence in split_sentences(text):
        reasons: list[str] = []
        unknown = [i for i in extract_citation_ids(sentence) if i not in papers_by_id]
        if unknown:
            reasons.append(f"cites unknown reference(s) {', '.join(unknown)}")
        numbers = unverified_statistics(sentence, allowed_source_text)
        if numbers:
            reasons.append(f"number(s) {', '.join(numbers)} not found in the verified sources")
        if reasons:
            problems.append(f"“{shorten(sentence, 140)}” - {'; '.join(reasons)}.")
    return problems


def sanitize_citations(text: str, valid_ids: set[str]) -> str:
    """Remove citation markers that point to references that do not exist."""

    def fix(match: re.Match) -> str:
        ids = [part.strip() for part in match.group(1).split(",")]
        good = [i for i in ids if i in valid_ids]
        if len(good) == len(ids):
            return match.group(0)
        return f"[{', '.join(good)}]" if good else UNVERIFIED_MARK

    return CITE_RE.sub(fix, text)
