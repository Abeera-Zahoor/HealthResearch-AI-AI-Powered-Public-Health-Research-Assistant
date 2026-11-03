"""Classify the study design of a paper from its PubMed/Europe PMC publication types.

Rank (higher = generally stronger evidence for an intervention question):
  7 systematic review / meta-analysis, 6 randomized controlled trial, 5 guideline,
  4 cohort / non-randomized trial / observational, 3 case-control, cross-sectional or narrative review,
  2 other / unspecified, 1 case report, editorial, letter, comment.

The rank is a rough screening aid. It is NOT a quality appraisal of an individual study.
"""
from __future__ import annotations

import re

# (publication type as used by PubMed, label, rank) - checked in this order.
_PUBTYPE_RULES: list[tuple[str, str, int]] = [
    ("meta-analysis", "Meta-analysis", 7),
    ("systematic review", "Systematic review", 7),
    ("randomized controlled trial", "Randomized controlled trial", 6),
    ("practice guideline", "Guideline", 5),
    ("guideline", "Guideline", 5),
    ("controlled clinical trial", "Non-randomized controlled trial", 4),
    ("clinical trial", "Clinical trial", 4),
    ("observational study", "Observational study", 4),
    ("cohort", "Cohort study", 4),
    ("case-control", "Case-control study", 3),
    ("cross-sectional", "Cross-sectional study", 3),
    ("review", "Narrative review", 3),
    ("case reports", "Case report", 1),
    ("editorial", "Editorial", 1),
    ("comment", "Comment", 1),
    ("letter", "Letter", 1),
    ("news", "News item", 1),
    ("preprint", "Preprint", 2),
]

# (regex on title/abstract, label, rank) - used only when no publication type matched.
_TEXT_RULES: list[tuple[str, str, int]] = [
    (r"\bmeta-?analy", "Meta-analysis", 7),
    (r"\bsystematic review", "Systematic review", 7),
    (r"\brandomi[sz]ed\b", "Randomized controlled trial", 6),
    (r"\bcohort\b", "Cohort study", 4),
    (r"\bcase-control\b", "Case-control study", 3),
    (r"\bcross-sectional\b", "Cross-sectional study", 3),
]


def classify_study_design(pub_types: list[str], title: str = "", abstract: str = "") -> tuple[str, int, bool]:
    """Return (label, rank, inferred_from_text)."""
    lowered = [t.lower() for t in pub_types]
    best: tuple[str, int] | None = None
    for needle, label, rank in _PUBTYPE_RULES:
        if any(needle in t for t in lowered):
            if best is None or rank > best[1]:
                best = (label, rank)
    if best:
        return best[0], best[1], False

    haystack = f"{title}\n{abstract}".lower()
    for pattern, label, rank in _TEXT_RULES:
        if re.search(pattern, haystack):
            return label, rank, True
    return "Not specified", 2, False
