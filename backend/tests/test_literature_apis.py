import httpx
import pytest

from app.apis import SourceError
from app.apis.europepmc import parse_europepmc_item
from app.apis.http import get_with_retry, scrub
from app.apis.pubmed import PubMedClient, parse_pubmed_xml
from tests.helpers import EPMC_ONLY_ITEM, epmc_item, make_clients, pubmed_xml


def test_parse_pubmed_xml_extracts_real_fields():
    papers = parse_pubmed_xml(pubmed_xml(["90000001", "90000003"]))
    first, second = papers
    assert first.pmid == "90000001" and first.year == 2021 and first.journal == "Journal of Test Fixtures"
    assert first.doi == "10.9999/fixture.001"
    assert first.abstract.startswith("BACKGROUND: Depression is common")
    assert first.study_design == "Randomized controlled trial" and first.sources == ["PubMed"]
    assert first.url == "https://pubmed.ncbi.nlm.nih.gov/90000001/"
    assert not second.has_abstract


def test_parse_pubmed_xml_rejects_garbage():
    with pytest.raises(SourceError):
        parse_pubmed_xml("<not-xml")


def test_parse_europepmc_cleans_html_and_ids():
    paper = parse_europepmc_item(EPMC_ONLY_ITEM)
    assert paper is not None
    assert "<i>" not in paper.title and "<h4>" not in paper.abstract
    assert paper.pmid is None and paper.pmcid == "PMC9000004"
    assert paper.url is not None and paper.url.startswith("https://europepmc.org/article/PMC/PMC9000004")
    med = parse_europepmc_item(epmc_item("90000001"))
    assert med is not None and med.pmid == "90000001" and not med.title.endswith(".")
    assert parse_europepmc_item({"id": "1", "source": "MED"}) is None


def test_pubmed_search_and_fetch_via_mock_server():
    pubmed, _, http = make_clients()
    assert pubmed.search("exercise depression", 5) == ["90000001", "90000002", "90000003"]
    assert [p.pmid for p in pubmed.fetch(["90000002"])] == ["90000002"]
    http.close()


def test_europepmc_lookup_matches_identifier():
    _, epmc, http = make_clients()
    assert epmc.lookup(pmid="90000002").pmid == "90000002"
    assert epmc.lookup(pmid="11111111") is None
    assert epmc.lookup() is None
    http.close()


def test_europepmc_excludes_preprints_by_default():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["query"])
        return httpx.Response(200, json={"resultList": {"result": []}})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    from app.apis import EuropePMCClient

    client = EuropePMCClient(http, "https://x.test", backoff=0, sleep=lambda s: None)
    client.search("asthma", 5)
    client.search("asthma", 5, include_preprints=True)
    assert seen == ["(asthma) NOT (SRC:PPR)", "asthma"]


def test_retry_then_success_and_final_failure():
    calls = {"n": 0}

    def flaky(request):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200, json={"ok": True})

    http = httpx.Client(transport=httpx.MockTransport(flaky))
    sleeps = []
    response = get_with_retry(http, "https://x.test", params=None, source="Test", backoff=1, sleep=sleeps.append)
    assert response.json() == {"ok": True} and calls["n"] == 3 and sleeps == [1, 2]

    always_bad = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    with pytest.raises(SourceError, match="HTTP 404"):
        get_with_retry(always_bad, "https://x.test", params=None, source="Test", sleep=lambda s: None)


def test_api_key_never_appears_in_error_text():
    assert "SECRET" not in scrub("failed https://x?db=pubmed&api_key=SECRET123&y=1")

    def boom(request):
        raise httpx.ConnectError(f"cannot connect to {request.url}")

    http = httpx.Client(transport=httpx.MockTransport(boom))
    client = PubMedClient(http, "https://x.test", api_key="SECRET123", min_interval=0, backoff=0, sleep=lambda s: None)
    with pytest.raises(SourceError) as info:
        client.search("asthma", 3)
    assert "SECRET123" not in str(info.value)
