"""Test helpers: fake PubMed / Europe PMC servers (httpx.MockTransport) and a scripted fake LLM.

IMPORTANT: every paper below is a made-up TEST FIXTURE (fake PMIDs 9000000x, fake DOIs).
They exist only so tests can run offline. The application itself never contains fake papers.
"""
from __future__ import annotations

import json
from typing import Callable, Optional

import httpx

from app.apis import EuropePMCClient, PubMedClient
from app.config import Settings
from app.schemas import LLMInfo

ABSTRACT_RCT = (
    "Depression is common in adults. We randomized 120 adults to a 12-week supervised aerobic exercise program or usual care. "
    "Depressive symptom scores fell by 35% in the exercise group compared with 12% in the control group. "
    "Supervised aerobic exercise reduced depressive symptoms in adults over 12 weeks."
)
ABSTRACT_META = (
    "We pooled prospective cohort studies of physical activity and depression. "
    "Physical activity was associated with a lower risk of depression across 25 cohort studies."
)

FIXTURE_ARTICLES = {
    "90000001": {
        "title": "Test fixture: Aerobic exercise for depressive symptoms in adults, a randomized trial",
        "journal": "Journal of Test Fixtures",
        "year": "2021",
        "doi": "10.9999/fixture.001",
        "types": ["Journal Article", "Randomized Controlled Trial"],
        "abstract": [("BACKGROUND", "Depression is common in adults."),
                     ("METHODS", "We randomized 120 adults to a 12-week supervised aerobic exercise program or usual care."),
                     ("RESULTS", "Depressive symptom scores fell by 35% in the exercise group compared with 12% in the control group."),
                     ("CONCLUSIONS", "Supervised aerobic exercise reduced depressive symptoms in adults over 12 weeks.")],
    },
    "90000002": {
        "title": "Test fixture: Physical activity and risk of depression, a meta-analysis of cohort studies",
        "journal": "Fixture Reviews",
        "year": "2019",
        "doi": "10.9999/fixture.002",
        "types": ["Journal Article", "Meta-Analysis", "Systematic Review"],
        "abstract": [("", "We pooled prospective cohort studies of physical activity and depression."),
                     ("", "Physical activity was associated with a lower risk of depression across 25 cohort studies.")],
    },
    "90000003": {
        "title": "Test fixture: Editorial on exercise and mood",
        "journal": "Fixture Letters",
        "year": "2020",
        "doi": "10.9999/fixture.003",
        "types": ["Editorial"],
        "abstract": [],
    },
}


def pubmed_xml(pmids: list[str]) -> str:
    blocks = []
    for pmid in pmids:
        a = FIXTURE_ARTICLES[pmid]
        abstract = ""
        if a["abstract"]:
            parts = "".join(
                f'<AbstractText Label="{lab}">{txt}</AbstractText>' if lab else f"<AbstractText>{txt}</AbstractText>"
                for lab, txt in a["abstract"]
            )
            abstract = f"<Abstract>{parts}</Abstract>"
        types = "".join(f"<PublicationType>{t}</PublicationType>" for t in a["types"])
        blocks.append(
            f"""<PubmedArticle><MedlineCitation><PMID Version="1">{pmid}</PMID><Article>
            <Journal><JournalIssue><PubDate><Year>{a['year']}</Year></PubDate></JournalIssue><Title>{a['journal']}</Title></Journal>
            <ArticleTitle>{a['title']}</ArticleTitle>{abstract}
            <AuthorList><Author><LastName>Fixture</LastName><Initials>A</Initials></Author></AuthorList>
            <PublicationTypeList>{types}</PublicationTypeList></Article></MedlineCitation>
            <PubmedData><ArticleIdList><ArticleId IdType="pubmed">{pmid}</ArticleId>
            <ArticleId IdType="doi">{a['doi']}</ArticleId></ArticleIdList></PubmedData></PubmedArticle>"""
        )
    return f'<?xml version="1.0"?><PubmedArticleSet>{"".join(blocks)}</PubmedArticleSet>'


def epmc_item(pmid: str) -> dict:
    a = FIXTURE_ARTICLES[pmid]
    return {
        "id": pmid, "source": "MED", "pmid": pmid, "doi": a["doi"], "title": a["title"] + ".",
        "authorString": "Fixture A.", "journalInfo": {"yearOfPublication": int(a["year"]), "journal": {"title": a["journal"]}},
        "pubYear": a["year"], "abstractText": " ".join(t for _, t in a["abstract"]),
        "pubTypeList": {"pubType": a["types"]}, "citedByCount": 3,
    }


EPMC_ONLY_ITEM = {
    "id": "PMC9000004", "source": "PMC", "pmcid": "PMC9000004", "doi": "10.9999/fixture.004",
    "title": "Test fixture: Community walking groups and low mood <i>pilot</i> study",
    "authorString": "Fixture B, Fixture C.", "pubYear": "2022",
    "journalInfo": {"journal": {"title": "Fixture Community Health"}},
    "abstractText": "<h4>Abstract</h4> Participants joined community walking groups for 8 weeks. Participants reported better mood after the walking program.",
    "pubTypeList": {"pubType": ["research-article"]},
}


def fixture_handler(
    pubmed_ids: Optional[list[str]] = None,
    epmc_pmids: Optional[list[str]] = None,
    epmc_extra: Optional[list[dict]] = None,
    fail_pubmed: bool = False,
    fail_epmc: bool = False,
) -> Callable[[httpx.Request], httpx.Response]:
    pubmed_ids = ["90000001", "90000002", "90000003"] if pubmed_ids is None else pubmed_ids
    epmc_pmids = ["90000001", "90000002", "90000003"] if epmc_pmids is None else epmc_pmids
    epmc_extra = [EPMC_ONLY_ITEM] if epmc_extra is None else epmc_extra

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        params = request.url.params
        if "eutils" in url or "entrez" in url:
            if fail_pubmed:
                return httpx.Response(500, text="boom")
            if request.url.path.endswith("esearch.fcgi"):
                return httpx.Response(200, json={"esearchresult": {"idlist": pubmed_ids}})
            if request.url.path.endswith("efetch.fcgi"):
                wanted = [i for i in params["id"].split(",") if i in FIXTURE_ARTICLES]
                return httpx.Response(200, text=pubmed_xml(wanted))
        if "europepmc" in url:
            if fail_epmc:
                return httpx.Response(503, text="down")
            query = params["query"]
            if query.startswith("EXT_ID:"):
                pmid = query.split()[0].split(":")[1]
                items = [epmc_item(pmid)] if pmid in epmc_pmids else []
            else:
                items = [epmc_item(p) for p in epmc_pmids] + epmc_extra
            return httpx.Response(200, json={"resultList": {"result": items}})
        return httpx.Response(404, text="unexpected URL in test: " + url)

    return handler


def make_clients(**kwargs) -> tuple[PubMedClient, EuropePMCClient, httpx.Client]:
    http = httpx.Client(transport=httpx.MockTransport(fixture_handler(**kwargs)))
    pubmed = PubMedClient(http, "https://eutils.example.test/entrez/eutils", min_interval=0, backoff=0, sleep=lambda s: None)
    epmc = EuropePMCClient(http, "https://www.europepmc.example.test/rest", backoff=0, sleep=lambda s: None)
    return pubmed, epmc, http


def make_settings(tmp_path, **overrides) -> Settings:
    values = dict(llm_provider="none", database_path=str(tmp_path / "test.db"), include_preprints=False)
    values.update(overrides)
    return Settings(_env_file=None, **values)


class FakeLLM:
    """Scripted stand-in for LLMClient. `script` maps a task name to a dict (or a callable returning one)."""

    def __init__(self, script: Optional[dict] = None, enabled: bool = True) -> None:
        self.script = script or {}
        self._enabled = enabled
        self.calls: list[tuple[str, str]] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def info(self) -> LLMInfo:
        return LLMInfo(enabled=self._enabled, provider="fake", model="fake-model")

    @staticmethod
    def task_of(system: str) -> str:
        if "literature-search queries" in system:
            return "queries"
        if "fact-checking" in system:
            return "judge"
        if "health education content" in system:
            return "education"
        return "analysis"

    def complete_json(self, system: str, user: str, *, max_tokens=None) -> dict:
        task = self.task_of(system)
        self.calls.append((task, user))
        response = self.script.get(task)
        if response is None:
            from app.llm import LLMError

            raise LLMError(f"no scripted response for {task}")
        if isinstance(response, Exception):
            raise response
        return response(user) if callable(response) else response
