"""End-to-end tests of the whole four-agent workflow (offline: mocked PubMed/Europe PMC and a scripted LLM)."""
import pytest

from app.db import Database
from app.pipeline import Pipeline
from app.schemas import Audience, OutputType, ResearchRequest
from tests.helpers import FakeLLM, make_clients, make_settings

QUESTION = "Does regular physical activity reduce the risk of depression in adults?"


def build(tmp_path, llm=None, **client_kwargs):
    settings = make_settings(tmp_path)
    db = Database(settings.database_path)
    db.init()
    pubmed, epmc, http = make_clients(**client_kwargs)
    return Pipeline(settings, db, http=http, pubmed=pubmed, europepmc=epmc, llm=llm or FakeLLM(enabled=False)), db


def run_once(pipeline, output_type=OutputType.research_summary):
    run = pipeline.create_run(ResearchRequest(question=QUESTION, output_type=output_type))
    pipeline.execute(run.id)
    return pipeline.db.get_run(run.id)


def test_full_workflow_without_llm(tmp_path):
    pipeline, db = build(tmp_path)
    run = run_once(pipeline)
    assert run.status == "completed" and run.error is None
    assert [s.status for s in run.steps] == ["completed"] * 4
    assert len(run.papers) == 4 and run.analysis.mode == "extractive"
    assert run.citations.counts["claims_total"] == len(run.analysis.findings) > 0
    assert run.citations.counts["claims_unsupported"] == 0  # extractive claims are verbatim abstract sentences
    assert run.output.mode == "template" and run.output.content and run.output.cited_ref_ids
    assert {p.ref_id for p in run.papers} >= set(run.output.cited_ref_ids)
    assert run.llm.enabled is False
    assert db.list_runs()[0].paper_count == 4


def test_full_workflow_with_llm_catches_a_hallucination(tmp_path):
    llm = FakeLLM({
        "queries": {"queries": ["exercise depression"]},
        "analysis": lambda user: {
            "summary": "Trials and cohorts point the same way [S1].",
            "findings": [
                {"claim": "Supervised aerobic exercise reduced depressive symptoms in adults over 12 weeks.", "source_ids": ["S1"], "strength": "moderate", "caveat": "One trial"},
                {"claim": "Exercise cut depression rates by 99% in every adult.", "source_ids": ["S1"], "strength": "strong", "caveat": ""},
            ],
            "evidence_gaps": [], "limitations": [], "conflicting_evidence": [],
        },
        "judge": lambda user: {"judgements": [
            {"claim_index": 1, "verdict": "supported", "source_id": "S1", "quote": "Supervised aerobic exercise reduced depressive symptoms in adults over 12 weeks.", "reason": "Stated."},
            {"claim_index": 2, "verdict": "supported", "source_id": "S1", "quote": "cut depression rates by 99%", "reason": "Fabricated."},
        ]},
        "education": {"title": "Exercise and mood", "content": "A trial found supervised aerobic exercise reduced depressive symptoms over 12 weeks [S1]."},
    })
    pipeline, _ = build(tmp_path, llm)
    run = run_once(pipeline, OutputType.public_health_article)
    assert run.status == "completed" and run.analysis.mode == "llm" and run.citations.llm_used
    assert [c.support for c in run.citations.claims] == ["supported", "unsupported"]
    assert run.citations.claims[1].unverified_numbers == ["99"]
    assert run.output.mode == "llm" and "99" not in run.output.content  # the fabricated claim never reaches the article
    assert any("could not be verified" in f for f in run.citations.flags)


def test_no_papers_found_completes_with_warning_and_skips(tmp_path):
    pipeline, _ = build(tmp_path, pubmed_ids=[], epmc_pmids=[], epmc_extra=[])
    run = run_once(pipeline)
    assert run.status == "completed" and run.papers == [] and run.output is None
    assert [s.status for s in run.steps] == ["completed", "skipped", "skipped", "skipped"]
    assert any("No papers were found" in w for w in run.warnings)


def test_sources_unreachable_fails_cleanly(tmp_path):
    pipeline, _ = build(tmp_path, fail_pubmed=True, fail_epmc=True)
    run = run_once(pipeline)
    assert run.status == "failed" and "Could not reach PubMed or Europe PMC" in run.error
    assert [s.status for s in run.steps] == ["failed", "skipped", "skipped", "skipped"]


def test_misconfigured_llm_warns_and_still_works(tmp_path):
    settings = make_settings(tmp_path, llm_provider="anthropic", llm_api_key="")
    db = Database(settings.database_path)
    db.init()
    pubmed, epmc, http = make_clients()
    pipeline = Pipeline(settings, db, http=http, pubmed=pubmed, europepmc=epmc)
    run = run_once(pipeline)
    assert run.status == "completed" and any("AI writing is disabled" in w for w in run.warnings)
