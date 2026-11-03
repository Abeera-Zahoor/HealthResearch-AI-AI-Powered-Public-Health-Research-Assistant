"""Agent 1 - Research Agent: finds real papers in PubMed and Europe PMC.

The LLM (if enabled) only helps to write search queries. Every paper, abstract, identifier
and link comes straight from the two literature APIs - never from the model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

from ..apis import EuropePMCClient, PubMedClient, SourceError
from ..llm import LLMClient, LLMError
from ..paper_utils import finalize_paper, normalize_title
from ..schemas import Paper
from ..text_utils import extract_keywords
from .base import AgentError

MAX_QUERIES = 3
TITLE_MATCH_THRESHOLD = 0.85

QUERY_SYSTEM = (
    "You write literature-search queries for PubMed. Return JSON: "
    '{"queries": ["...", "..."]} with 2 short keyword queries (3-8 words each, plain keywords, '
    "optionally joined with AND / OR). Do not answer the question. Do not invent anything."
)


def titles_match(a: str, b: str) -> bool:
    return SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio() >= TITLE_MATCH_THRESHOLD


def identity_keys(paper: Paper) -> list[str]:
    keys = []
    if paper.pmid:
        keys.append(f"pmid:{paper.pmid}")
    if paper.doi:
        keys.append(f"doi:{paper.doi}")
    if paper.title:
        keys.append(f"title:{normalize_title(paper.title)}")
    return keys


def merge_papers(a: Paper, b: Paper) -> Paper:
    """Combine two records of the same paper, filling gaps and noting disagreements."""
    merged = a.model_copy(deep=True)
    if a.title and b.title and not titles_match(a.title, b.title):
        merged.metadata_notes.append(
            f"Title differs between {', '.join(a.sources)} and {', '.join(b.sources)} records."
        )
    if a.doi and b.doi and a.doi != b.doi:
        merged.metadata_notes.append(f"DOI differs between databases ({a.doi} vs {b.doi}).")
    for name in ("journal", "year", "doi", "pmid", "pmcid", "epmc_source", "epmc_id"):
        if not getattr(merged, name) and getattr(b, name):
            setattr(merged, name, getattr(b, name))
    if len(b.abstract) > len(merged.abstract):
        merged.abstract = b.abstract
    if not merged.authors:
        merged.authors = list(b.authors)
    merged.pub_types = list(dict.fromkeys([*merged.pub_types, *b.pub_types]))
    merged.sources = list(dict.fromkeys([*merged.sources, *b.sources]))
    if b.cited_by_count is not None:
        merged.cited_by_count = max(merged.cited_by_count or 0, b.cited_by_count)
    return finalize_paper(merged)


class _Pool:
    """Collects candidate papers, merging duplicates and adding up reciprocal-rank scores."""

    def __init__(self) -> None:
        self.papers: list[Paper] = []
        self.scores: list[float] = []
        self._index: dict[str, int] = {}

    def add(self, paper: Paper, rank: int) -> None:
        keys = identity_keys(paper)
        slot = next((self._index[k] for k in keys if k in self._index), None)
        score = 1.0 / (10 + rank)
        if slot is None:
            slot = len(self.papers)
            self.papers.append(paper)
            self.scores.append(0.0)
        else:
            self.papers[slot] = merge_papers(self.papers[slot], paper)
        self.scores[slot] += score
        for key in identity_keys(self.papers[slot]):
            self._index.setdefault(key, slot)


def ranking_score(paper: Paper, relevance: float) -> float:
    """Heuristic ordering. Papers without an abstract cannot be analysed, so they rank below all papers
    that have one; within each group: relevance (rank fusion across queries/databases), then study design."""
    score = relevance + 0.01 * paper.evidence_rank
    if paper.has_abstract:
        score += 1.0
    if paper.is_preprint:
        score -= 0.05
    if paper.is_retracted:
        score -= 5
    return score


@dataclass
class ResearchOutcome:
    queries: list[str]
    papers: list[Paper]
    warnings: list[str] = field(default_factory=list)


class ResearchAgent:
    key = "research"
    name = "Research Agent"

    def __init__(
        self,
        pubmed: PubMedClient,
        europepmc: EuropePMCClient,
        llm: Optional[LLMClient] = None,
        include_preprints: bool = False,
    ) -> None:
        self.pubmed = pubmed
        self.europepmc = europepmc
        self.llm = llm
        self.include_preprints = include_preprints

    # ------------------------------------------------------------------
    def build_queries(self, question: str) -> tuple[list[str], list[str]]:
        warnings: list[str] = []
        queries: list[str] = []
        if self.llm is not None and self.llm.enabled:
            try:
                data = self.llm.complete_json(QUERY_SYSTEM, f"Research question: {question}", max_tokens=300)
                for item in data.get("queries", []):
                    if isinstance(item, str) and 3 <= len(item.strip()) <= 200:
                        queries.append(" ".join(item.split()))
            except LLMError as exc:
                warnings.append(f"The LLM could not write search queries ({exc}); keyword search was used instead.")
        keywords = extract_keywords(question, limit=6)
        if keywords:
            queries.append(" ".join(keywords))
            if len(keywords) > 3:
                queries.append(" ".join(keywords[:3]))
        if not queries:
            queries.append(question)
        unique = list(dict.fromkeys(q.strip() for q in queries if q.strip()))
        return unique[:MAX_QUERIES], warnings

    def run(self, question: str, max_papers: int) -> ResearchOutcome:
        queries, warnings = self.build_queries(question)
        pool = _Pool()
        pubmed_ok = epmc_ok = False
        errors: list[str] = []

        pubmed_ranks: dict[str, int] = {}
        for query in queries:
            try:
                for rank, pmid in enumerate(self.pubmed.search(query, max_papers)):
                    pubmed_ranks[pmid] = min(rank, pubmed_ranks.get(pmid, rank))
                pubmed_ok = True
            except SourceError as exc:
                errors.append(str(exc))
        if pubmed_ranks:
            try:
                fetched = {p.pmid: p for p in self.pubmed.fetch(list(pubmed_ranks)) if p.pmid}
                for pmid, rank in pubmed_ranks.items():
                    if pmid in fetched:
                        pool.add(fetched[pmid], rank)
            except SourceError as exc:
                pubmed_ok = False
                errors.append(str(exc))

        for query in queries:
            try:
                for rank, paper in enumerate(self.europepmc.search(query, max_papers, self.include_preprints)):
                    pool.add(paper, rank)
                epmc_ok = True
            except SourceError as exc:
                errors.append(str(exc))

        if not pubmed_ok and not epmc_ok:
            detail = " ".join(dict.fromkeys(errors)) or "Unknown error."
            raise AgentError(
                "Could not reach PubMed or Europe PMC. Check your internet connection and try again. " + detail
            )
        for message in dict.fromkeys(errors):
            warnings.append(f"{message} Results may be incomplete.")

        candidates = [
            (ranking_score(p, s), p) for p, s in zip(pool.papers, pool.scores) if not p.is_retraction_notice
        ]
        skipped = len(pool.papers) - len(candidates)
        if skipped:
            warnings.append(f"{skipped} retraction notice(s) were excluded from the results.")
        candidates.sort(key=lambda pair: pair[0], reverse=True)
        papers = [p for _, p in candidates[:max_papers]]
        for number, paper in enumerate(papers, start=1):
            paper.ref_id = f"S{number}"
        if any(p.is_retracted for p in papers):
            warnings.append("At least one retrieved paper has been retracted. It is flagged and excluded from the analysis.")
        return ResearchOutcome(queries=queries, papers=papers, warnings=warnings)
