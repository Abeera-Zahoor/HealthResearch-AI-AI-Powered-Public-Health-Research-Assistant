"""Europe PMC REST client (free, no key). Used for search and for cross-checking records."""
from __future__ import annotations

import html
import re
import time
from typing import Any, Callable, Optional

import httpx

from ..paper_utils import finalize_paper, normalize_doi
from ..schemas import Paper
from .http import SourceError, get_with_retry

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(value: Any) -> str:
    if not value:
        return ""
    return " ".join(html.unescape(_TAG_RE.sub(" ", str(value))).split())


def _year(item: dict) -> Optional[int]:
    candidates = [
        item.get("pubYear"),
        (item.get("journalInfo") or {}).get("yearOfPublication"),
        str(item.get("firstPublicationDate") or "")[:4],
    ]
    for value in candidates:
        if value and str(value).isdigit():
            return int(value)
    return None


def parse_europepmc_item(item: dict) -> Optional[Paper]:
    title = _clean(item.get("title"))
    if not title:
        return None
    source = str(item.get("source") or "") or None
    epmc_id = str(item.get("id") or "") or None
    pmid = str(item.get("pmid") or "") or (epmc_id if source == "MED" else None)

    authors = [
        _clean(a.get("fullName"))
        for a in (item.get("authorList") or {}).get("author", [])
        if isinstance(a, dict) and a.get("fullName")
    ]
    if not authors and item.get("authorString"):
        authors = [a.strip() for a in _clean(item["authorString"]).rstrip(".").split(", ") if a.strip()]

    pub_types = (item.get("pubTypeList") or {}).get("pubType", [])
    if isinstance(pub_types, str):
        pub_types = [pub_types]

    cited = item.get("citedByCount")
    paper = Paper(
        title=title.rstrip("."),
        authors=authors,
        journal=_clean((item.get("journalInfo") or {}).get("journal", {}).get("title")) or _clean(item.get("journalTitle")) or None,
        year=_year(item),
        abstract=_clean(item.get("abstractText")),
        doi=normalize_doi(item.get("doi")),
        pmid=pmid,
        pmcid=str(item.get("pmcid") or "") or None,
        epmc_source=source,
        epmc_id=epmc_id,
        sources=["Europe PMC"],
        pub_types=[_clean(t) for t in pub_types if _clean(t)],
        cited_by_count=int(cited) if isinstance(cited, (int, str)) and str(cited).isdigit() else None,
    )
    return finalize_paper(paper)


class EuropePMCClient:
    def __init__(
        self,
        client: httpx.Client,
        base_url: str,
        backoff: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.backoff = backoff
        self._sleep = sleep

    def _search(self, query: str, page_size: int, result_type: str = "core") -> list[dict]:
        response = get_with_retry(
            self.client,
            f"{self.base_url}/search",
            params={"query": query, "format": "json", "resultType": result_type, "pageSize": page_size},
            source="Europe PMC",
            backoff=self.backoff,
            sleep=self._sleep,
        )
        try:
            return list(response.json().get("resultList", {}).get("result", []))
        except (ValueError, AttributeError) as exc:
            raise SourceError("Europe PMC returned an unexpected response.") from exc

    def search(self, query: str, page_size: int, include_preprints: bool = False) -> list[Paper]:
        full_query = query if include_preprints else f"({query}) NOT (SRC:PPR)"
        papers = (parse_europepmc_item(item) for item in self._search(full_query, page_size))
        return [p for p in papers if p is not None]

    def lookup(self, *, pmid: Optional[str] = None, doi: Optional[str] = None) -> Optional[Paper]:
        """Find one specific record by identifier (used to cross-check PubMed records)."""
        if pmid:
            query = f"EXT_ID:{pmid} AND SRC:MED"
        elif doi:
            query = f'DOI:"{doi}"'
        else:
            return None
        for item in self._search(query, 3):
            paper = parse_europepmc_item(item)
            if paper is None:
                continue
            if pmid and paper.pmid == pmid:
                return paper
            if doi and paper.doi == normalize_doi(doi):
                return paper
        return None
