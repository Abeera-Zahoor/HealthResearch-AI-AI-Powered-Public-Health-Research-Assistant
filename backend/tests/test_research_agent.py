import pytest

from app.agents import AgentError, ResearchAgent
from app.agents.research import merge_papers, titles_match
from app.llm import LLMError
from app.paper_utils import finalize_paper
from app.schemas import Paper
from tests.helpers import FakeLLM, make_clients

QUESTION = "Does regular physical activity reduce the risk of depression in adults?"


def make_agent(llm=None, **client_kwargs):
    pubmed, epmc, _ = make_clients(**client_kwargs)
    return ResearchAgent(pubmed, epmc, llm)


def test_retrieves_merges_and_numbers_papers():
    outcome = make_agent().run(QUESTION, max_papers=10)
    papers = outcome.papers
    assert [p.ref_id for p in papers] == [f"S{i}" for i in range(1, len(papers) + 1)]
    assert len(papers) == 4  # 3 shared records merged + 1 Europe PMC-only record
    merged = next(p for p in papers if p.pmid == "90000001")
    assert merged.sources == ["PubMed", "Europe PMC"]
    assert merged.url and merged.url.startswith("https://pubmed.ncbi.nlm.nih.gov/")
    # Ranking: every paper with an abstract comes before the abstract-less editorial.
    assert papers[-1].study_design == "Editorial" and all(p.has_abstract for p in papers[:-1])


def test_every_paper_comes_from_the_apis_not_the_model():
    llm = FakeLLM({"queries": {"queries": ["exercise depression adults"]}})
    outcome = make_agent(llm).run(QUESTION, 10)
    assert outcome.queries[0] == "exercise depression adults"
    assert all(p.pmid or p.pmcid for p in outcome.papers)
    assert all("fixture" in p.title.lower() for p in outcome.papers)


def test_llm_failure_falls_back_to_keywords_with_warning():
    outcome = make_agent(FakeLLM({"queries": LLMError("quota")})).run(QUESTION, 5)
    assert outcome.queries[0].startswith("regular physical activity")
    assert any("keyword search" in w for w in outcome.warnings)


def test_one_source_down_still_returns_results_with_warning():
    outcome = make_agent(fail_epmc=True).run(QUESTION, 10)
    assert len(outcome.papers) == 3
    assert any("Europe PMC" in w and "incomplete" in w for w in outcome.warnings)


def test_both_sources_down_raises_readable_error():
    with pytest.raises(AgentError, match="Could not reach PubMed or Europe PMC"):
        make_agent(fail_pubmed=True, fail_epmc=True).run(QUESTION, 10)


def test_no_results_is_not_an_error():
    outcome = make_agent(pubmed_ids=[], epmc_pmids=[], epmc_extra=[]).run(QUESTION, 10)
    assert outcome.papers == []


def test_max_papers_is_respected():
    assert len(make_agent().run(QUESTION, 2).papers) == 2


def test_retraction_notices_are_dropped_and_retracted_papers_ranked_last():
    from tests.helpers import epmc_item

    notice = epmc_item("90000001")
    notice.update(id="90000009", pmid="90000009", title="Retraction: something else entirely",
                  pubTypeList={"pubType": ["Retraction of Publication"]}, doi="10.9999/r.9")
    retracted = epmc_item("90000002")
    retracted.update(id="90000008", pmid="90000008", title="A retracted paper on exercise and depression",
                     pubTypeList={"pubType": ["Retracted Publication"]}, doi="10.9999/r.8")
    outcome = make_agent(epmc_extra=[notice, retracted]).run(QUESTION, 20)
    assert all(not p.is_retraction_notice for p in outcome.papers)
    assert outcome.papers[-1].is_retracted
    assert any("retraction notice" in w for w in outcome.warnings)
    assert any("retracted" in w for w in outcome.warnings)


def test_merge_records_title_conflicts():
    a = finalize_paper(Paper(title="Exercise and mood in adults", pmid="1", sources=["PubMed"]))
    b = finalize_paper(Paper(title="Completely different paper about diet", pmid="1", sources=["Europe PMC"]))
    assert merge_papers(a, b).metadata_notes
    assert titles_match("Exercise and mood in adults.", "Exercise and mood in adults")
