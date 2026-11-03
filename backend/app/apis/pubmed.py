"""PubMed client (NCBI E-utilities): search for PMIDs, then fetch full records as XML."""
from __future__ import annotations

import re
import threading
import time
from typing import Callable, Optional

import httpx
from defusedxml import ElementTree as ET

from ..paper_utils import finalize_paper
from ..schemas import Paper
from .http import SourceError, get_with_retry

_YEAR_RE = re.compile(r"(?:19|20)\d{2}")


def _text(element) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def _year(article) -> Optional[int]:
    year = _text(article.find("Journal/JournalIssue/PubDate/Year"))
    if not year:
        match = _YEAR_RE.search(_text(article.find("Journal/JournalIssue/PubDate/MedlineDate")))
        year = match.group(0) if match else ""
    if not year:
        year = _text(article.find("ArticleDate/Year"))
    return int(year) if year.isdigit() else None


def parse_pubmed_xml(xml_text: str) -> list[Paper]:
    """Turn an efetch XML document into Paper objects. Records without a PMID or title are skipped."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise SourceError(f"PubMed returned XML that could not be read ({exc}).") from exc

    papers: list[Paper] = []
    for record in root.iter("PubmedArticle"):
        citation = record.find("MedlineCitation")
        article = citation.find("Article") if citation is not None else None
        if citation is None or article is None:
            continue
        pmid = _text(citation.find("PMID"))
        title = _text(article.find("ArticleTitle"))
        if not pmid or not title:
            continue

        parts: list[str] = []
        for node in article.findall("Abstract/AbstractText"):
            label = (node.get("Label") or "").strip()
            body = _text(node)
            if not body:
                continue
            parts.append(f"{label}: {body}" if label and label.upper() != "UNLABELLED" else body)

        authors: list[str] = []
        for author in article.findall("AuthorList/Author"):
            collective = _text(author.find("CollectiveName"))
            last = _text(author.find("LastName"))
            initials = _text(author.find("Initials"))
            name = collective or " ".join(p for p in (last, initials) if p)
            if name:
                authors.append(name)

        doi = pmcid = None
        for node in record.findall("PubmedData/ArticleIdList/ArticleId"):
            kind = (node.get("IdType") or "").lower()
            if kind == "doi" and not doi:
                doi = _text(node)
            elif kind == "pmc" and not pmcid:
                pmcid = _text(node)
        if not doi:
            for node in article.findall("ELocationID"):
                if (node.get("EIdType") or "").lower() == "doi":
                    doi = _text(node)
                    break

        paper = Paper(
            title=title,
            authors=authors,
            journal=_text(article.find("Journal/Title")) or None,
            year=_year(article),
            abstract=" ".join(parts),
            doi=doi,
            pmid=pmid,
            pmcid=pmcid,
            sources=["PubMed"],
            pub_types=[_text(n) for n in article.findall("PublicationTypeList/PublicationType") if _text(n)],
        )
        papers.append(finalize_paper(paper))
    return papers


class PubMedClient:
    def __init__(
        self,
        client: httpx.Client,
        base_url: str,
        api_key: str = "",
        email: str = "",
        min_interval: Optional[float] = None,
        backoff: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.email = email.strip()
        # NCBI allows 3 requests/second without a key and 10 with one.
        self.min_interval = min_interval if min_interval is not None else (0.11 if self.api_key else 0.34)
        self.backoff = backoff
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last_call = 0.0

    def _get(self, endpoint: str, params: dict) -> httpx.Response:
        with self._lock:  # also serialises calls, which keeps us under NCBI's rate limit
            wait = self.min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                self._sleep(wait)
            self._last_call = time.monotonic()
        params = {**params, "tool": "healthresearch-ai"}
        if self.api_key:
            params["api_key"] = self.api_key
        if self.email:
            params["email"] = self.email
        return get_with_retry(
            self.client,
            f"{self.base_url}/{endpoint}",
            params=params,
            source="PubMed",
            backoff=self.backoff,
            sleep=self._sleep,
        )

    def search(self, query: str, retmax: int) -> list[str]:
        """Return PMIDs, most relevant first."""
        response = self._get(
            "esearch.fcgi",
            {"db": "pubmed", "term": query, "retmax": retmax, "retmode": "json", "sort": "relevance"},
        )
        try:
            result = response.json()["esearchresult"]
        except (ValueError, KeyError, TypeError) as exc:
            raise SourceError("PubMed returned an unexpected search response.") from exc
        if result.get("ERROR"):
            raise SourceError(f"PubMed rejected the search: {result['ERROR']}")
        return [str(i) for i in result.get("idlist", [])]

    def fetch(self, pmids: list[str]) -> list[Paper]:
        papers: list[Paper] = []
        for start in range(0, len(pmids), 50):
            chunk = pmids[start : start + 50]
            response = self._get(
                "efetch.fcgi",
                {"db": "pubmed", "id": ",".join(chunk), "retmode": "xml", "rettype": "abstract"},
            )
            papers.extend(parse_pubmed_xml(response.text))
        return papers
