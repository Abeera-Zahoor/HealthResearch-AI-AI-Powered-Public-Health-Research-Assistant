"""Helpers that normalise paper metadata and build links.

All links are constructed here from identifiers returned by PubMed / Europe PMC.
No URL ever comes from an LLM.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import quote

from .schemas import Link, Paper
from .study_design import classify_study_design

_DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")


def normalize_doi(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    cleaned = _DOI_PREFIX_RE.sub("", doi.strip()).strip().rstrip(".").lower()
    return cleaned or None


def is_valid_doi(doi: Optional[str]) -> bool:
    return bool(doi and DOI_RE.match(doi))


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def build_links(paper: Paper) -> list[Link]:
    links: list[Link] = []
    if paper.pmid:
        links.append(Link(label="PubMed", url=f"https://pubmed.ncbi.nlm.nih.gov/{paper.pmid}/"))
    if paper.epmc_source and paper.epmc_id:
        links.append(
            Link(label="Europe PMC", url=f"https://europepmc.org/article/{paper.epmc_source}/{paper.epmc_id}")
        )
    if paper.doi and is_valid_doi(paper.doi):
        links.append(Link(label="Publisher (DOI)", url=f"https://doi.org/{quote(paper.doi, safe='/:;()<>-._')}"))
    if paper.pmcid:
        links.append(Link(label="Full text (PMC)", url=f"https://pmc.ncbi.nlm.nih.gov/articles/{paper.pmcid}/"))
    return links


def finalize_paper(paper: Paper) -> Paper:
    """Recompute derived fields (DOI, design, links, flags). Safe to call repeatedly."""
    paper.doi = normalize_doi(paper.doi)
    label, rank, inferred = classify_study_design(paper.pub_types, paper.title, paper.abstract)
    paper.study_design, paper.evidence_rank, paper.design_inferred = label, rank, inferred
    lowered = [t.lower() for t in paper.pub_types]
    if any("retracted publication" in t for t in lowered):
        paper.is_retracted = True
    if any(t.startswith("retraction of publication") for t in lowered):
        paper.is_retraction_notice = True
        paper.evidence_rank = 1
    if any("preprint" in t for t in lowered) or paper.epmc_source == "PPR":
        paper.is_preprint = True
        paper.evidence_rank = min(paper.evidence_rank, 2)
    paper.links = build_links(paper)
    paper.url = paper.links[0].url if paper.links else None
    return paper
