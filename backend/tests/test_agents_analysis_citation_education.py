from app.agents import CitationVerificationAgent, EvidenceAnalysisAgent, HealthEducationAgent, ResearchAgent
from app.agents.analysis import key_sentence, strength_ceiling
from app.llm import LLMError
from app.paper_utils import finalize_paper
from app.schemas import (
    Audience,
    CitationReport,
    ClaimVerification,
    EvidenceAnalysis,
    Finding,
    OutputType,
    Paper,
)
from app.verification import check_claim, quote_in_text, sanitize_citations
from tests.helpers import ABSTRACT_META, ABSTRACT_RCT, FakeLLM, make_clients

QUESTION = "Does regular physical activity reduce the risk of depression in adults?"


def retrieved_papers():
    pubmed, epmc, _ = make_clients()
    return ResearchAgent(pubmed, epmc).run(QUESTION, 10).papers


def paper(ref_id, abstract, **kw):
    return finalize_paper(Paper(ref_id=ref_id, title=kw.pop("title", "Exercise and depression"), abstract=abstract, pmid=kw.pop("pmid", "1"), **kw))


# ---------------------------------------------------------------- analysis
def test_key_sentence_prefers_conclusion_and_is_verbatim():
    abstract = "BACKGROUND: Context here. RESULTS: Scores fell. CONCLUSIONS: Exercise helped adults to feel better over 12 weeks of follow-up. More trials needed."
    sentence = key_sentence(abstract)
    assert sentence == "Exercise helped adults to feel better over 12 weeks of follow-up."
    assert sentence in abstract
    # very short conclusion sentences get the next sentence appended for context
    assert key_sentence("CONCLUSIONS: It worked. Larger trials are now needed to confirm this.") == "It worked. Larger trials are now needed to confirm this."


def test_extractive_analysis_uses_only_abstract_text():
    papers = retrieved_papers()
    analysis = EvidenceAnalysisAgent().run(QUESTION, papers)
    assert analysis.mode == "extractive" and analysis.findings
    corpus = " ".join(p.abstract for p in papers)
    for finding in analysis.findings:
        assert finding.claim in corpus
        assert all(i in {p.ref_id for p in papers} for i in finding.source_ids)
    assert any("abstract" in l.lower() for l in analysis.limitations)
    assert any("no abstract" in l for l in analysis.limitations)  # the editorial
    assert sum(analysis.study_design_counts.values()) == len(papers)


def test_gaps_flag_missing_trials_and_thin_evidence():
    weak = [paper("S1", "A cross-sectional survey of 40 adults found mood differences.", pub_types=["Journal Article"])]
    analysis = EvidenceAnalysisAgent().run(QUESTION, weak)
    gaps = " ".join(analysis.evidence_gaps)
    assert "thin evidence base" in gaps and "randomized controlled trials" in gaps


def test_no_abstracts_means_no_findings():
    analysis = EvidenceAnalysisAgent().run(QUESTION, [paper("S1", "")])
    assert analysis.findings == [] and "no abstract" in analysis.notes[0].lower()


def test_llm_strength_is_capped_by_study_design():
    papers = retrieved_papers()
    rct = next(p for p in papers if p.study_design == "Randomized controlled trial")
    cohort = paper("S9", "Cohort result sentence about exercise and depression.", pub_types=["Cohort Studies"])
    assert strength_ceiling([rct]) == "moderate" and strength_ceiling([cohort]) == "limited"
    llm = FakeLLM({"analysis": {
        "summary": f"Exercise may help [{rct.ref_id}].",
        "findings": [{"claim": f"Exercise reduced symptoms [{rct.ref_id}]", "source_ids": [rct.ref_id], "strength": "strong", "caveat": "small"}],
        "evidence_gaps": ["Long-term follow-up unknown"], "limitations": [], "conflicting_evidence": [],
    }})
    analysis = EvidenceAnalysisAgent(llm).run(QUESTION, papers)
    assert analysis.mode == "llm" and analysis.findings[0].strength == "moderate"
    assert "Long-term follow-up unknown" in analysis.evidence_gaps


def test_llm_failure_falls_back_to_extractive_with_note():
    analysis = EvidenceAnalysisAgent(FakeLLM({"analysis": LLMError("bad json")})).run(QUESTION, retrieved_papers())
    assert analysis.mode == "extractive" and any("LLM step failed" in n for n in analysis.notes)


# ---------------------------------------------------------------- claim checks
def test_check_claim_levels():
    papers = {"S1": paper("S1", ABSTRACT_RCT), "S2": paper("S2", ABSTRACT_META, pmid="2")}
    good = check_claim(1, "Supervised aerobic exercise reduced depressive symptoms in adults over 12 weeks.", ["S1"], papers)
    assert good.support == "supported" and good.unverified_numbers == []
    invented_number = check_claim(2, "Exercise reduced depressive symptoms in adults by 80%.", ["S1"], papers)
    assert invented_number.support == "partial" and invented_number.unverified_numbers == ["80"]
    unknown = check_claim(3, "Exercise reduced depressive symptoms in adults.", ["S7"], papers)
    assert unknown.support == "unsupported" and "do not exist" in " ".join(unknown.issues)
    no_source = check_claim(4, "Exercise cures everything.", [], papers)
    assert no_source.support == "unsupported"
    unrelated = check_claim(5, "Vitamin supplements prevent hair loss in teenagers.", ["S1"], papers)
    assert unrelated.support == "unsupported"
    no_abstract = check_claim(6, "Exercise helps.", ["S3"], {"S3": paper("S3", "")})
    assert no_abstract.support == "unsupported" and "abstract" in " ".join(no_abstract.issues)
    retracted = paper("S4", ABSTRACT_RCT, pub_types=["Retracted Publication"], pmid="4")
    assert check_claim(7, "Aerobic exercise reduced depressive symptoms.", ["S4"], {"S4": retracted}).support == "unsupported"


def test_quote_check_requires_verbatim_text():
    assert quote_in_text("Physical activity was associated with a lower risk", ABSTRACT_META)
    assert quote_in_text("Physical activity was ... across 25 cohort studies", ABSTRACT_META)
    assert not quote_in_text("Physical activity eliminates all depression", ABSTRACT_META)
    assert not quote_in_text("", ABSTRACT_META)


def test_sanitize_citations_removes_unknown_ids():
    assert sanitize_citations("A [S1] B [S9] C [S1, S9].", {"S1"}) == "A [S1] B [unverified source] C [S1]."


# ---------------------------------------------------------------- citation verification
def test_reference_checks_cross_verify_and_flag():
    pubmed, epmc, _ = make_clients()
    papers = ResearchAgent(pubmed, epmc).run(QUESTION, 10).papers
    report = CitationVerificationAgent(pubmed, epmc).run(papers, EvidenceAnalysis())
    by_title = {r.title: r for r in report.references}
    rct = next(r for t, r in by_title.items() if "randomized trial" in t)
    assert rct.status == "verified" and rct.cross_verified
    editorial = next(r for t, r in by_title.items() if "Editorial" in t)
    assert editorial.status == "partial"  # no abstract
    walking = next(r for t, r in by_title.items() if "walking" in t)
    assert walking.status == "partial" and not walking.cross_verified  # only one database, no PMID


def test_cross_check_detects_title_mismatch_and_missing_record():
    pubmed, epmc, _ = make_clients(epmc_pmids=["90000001"])
    agent = CitationVerificationAgent(pubmed, epmc)
    fake = finalize_paper(Paper(ref_id="S1", title="A totally different title about volcanoes", pmid="90000001", year=2021, journal="J", abstract=ABSTRACT_RCT, sources=["PubMed"]))
    assert agent.verify_reference(fake).status == "flagged"
    missing = finalize_paper(Paper(ref_id="S2", title="Anything", pmid="90000002", year=2021, journal="J", abstract=ABSTRACT_RCT, sources=["PubMed"]))
    result = agent.verify_reference(missing)
    assert result.status == "flagged" and "no record" in " ".join(c.detail for c in result.checks)


def test_cross_check_network_failure_is_a_warning_not_a_crash():
    pubmed, epmc, _ = make_clients(fail_epmc=True)
    agent = CitationVerificationAgent(pubmed, epmc)
    p = finalize_paper(Paper(ref_id="S1", title="Exercise", pmid="90000001", year=2021, journal="J", abstract=ABSTRACT_RCT, sources=["PubMed"]))
    result = agent.verify_reference(p)
    assert result.status == "partial" and "Could not cross-check" in " ".join(c.detail for c in result.checks)


def test_retracted_reference_is_flagged():
    agent = CitationVerificationAgent()
    p = paper("S1", ABSTRACT_RCT, pub_types=["Retracted Publication"], year=2020, journal="J", sources=["PubMed", "Europe PMC"])
    assert agent.verify_reference(p).status == "flagged"


def analysis_with(*claims):
    return EvidenceAnalysis(mode="llm", findings=[Finding(claim=c, source_ids=ids) for c, ids in claims])


def test_llm_judge_needs_a_real_quote():
    papers = [paper("S1", ABSTRACT_RCT)]
    claim = "Supervised aerobic exercise reduced depressive symptoms in adults over 12 weeks."
    good = FakeLLM({"judge": {"judgements": [{"claim_index": 1, "verdict": "supported", "source_id": "S1",
                                              "quote": "Supervised aerobic exercise reduced depressive symptoms in adults over 12 weeks.", "reason": "Stated."}]}})
    report = CitationVerificationAgent(llm=good).run(papers, analysis_with((claim, ["S1"])))
    assert report.llm_used and report.claims[0].support == "supported" and report.claims[0].method == "llm+heuristic"

    invented = FakeLLM({"judge": {"judgements": [{"claim_index": 1, "verdict": "supported", "source_id": "S1",
                                                  "quote": "Exercise completely cures depression in every adult.", "reason": "Sure."}]}})
    report = CitationVerificationAgent(llm=invented).run(papers, analysis_with((claim, ["S1"])))
    assert report.claims[0].support == "unsupported"
    assert any("quote was not found" in i for i in report.claims[0].issues)
    assert any("could not be verified" in f for f in report.flags)


def test_llm_judge_can_only_make_things_worse_and_failures_are_noted():
    papers = [paper("S1", ABSTRACT_RCT)]
    claim = "Supervised aerobic exercise reduced depressive symptoms in adults over 12 weeks."
    harsh = FakeLLM({"judge": {"judgements": [{"claim_index": 1, "verdict": "partial", "source_id": "S1",
                                               "quote": "Depression is common in adults", "reason": "Overstated."}]}})
    assert CitationVerificationAgent(llm=harsh).run(papers, analysis_with((claim, ["S1"]))).claims[0].support == "partial"
    broken = FakeLLM({"judge": LLMError("timeout")})
    report = CitationVerificationAgent(llm=broken).run(papers, analysis_with((claim, ["S1"])))
    assert not report.llm_used and any("judge failed" in n for n in report.notes)


def test_summary_with_unknown_citation_or_invented_number_is_flagged():
    papers = [paper("S1", ABSTRACT_RCT)]
    analysis = EvidenceAnalysis(mode="llm", summary="Exercise cut symptoms by 90% [S1]. Another study agrees [S5].",
                                findings=[Finding(claim="Aerobic exercise reduced depressive symptoms in adults.", source_ids=["S1"])])
    report = CitationVerificationAgent().run(papers, analysis)
    assert len(report.summary_issues) == 2 and report.counts["claims_total"] == 1


# ---------------------------------------------------------------- education
def approved_inputs():
    papers = [paper("S1", ABSTRACT_RCT, year=2021, journal="J")]
    analysis = EvidenceAnalysis(mode="llm", summary="One trial suggests benefit [S1].",
                                findings=[Finding(claim="Supervised aerobic exercise reduced depressive symptoms in adults over 12 weeks.", source_ids=["S1"], strength="moderate")],
                                evidence_gaps=["Only one trial"])
    citations = CitationReport(claims=[ClaimVerification(index=1, claim=analysis.findings[0].claim, source_ids=["S1"], support="supported")])
    return papers, analysis, citations


def test_education_refuses_to_write_when_nothing_is_verified():
    papers, analysis, citations = approved_inputs()
    citations.claims[0].support = "unsupported"
    out = HealthEducationAgent(FakeLLM()).run(QUESTION, Audience.general_public, OutputType.research_summary, papers, analysis, citations)
    assert out.mode == "none" and out.content == "" and out.flags and out.disclaimer


def test_education_template_mode_copies_verified_wording():
    papers, analysis, citations = approved_inputs()
    for output_type in OutputType:
        out = HealthEducationAgent().run(QUESTION, Audience.general_public, output_type, papers, analysis, citations)
        assert out.mode == "template" and out.content and out.cited_ref_ids == ["S1"], output_type
        assert analysis.findings[0].claim in out.content or output_type == OutputType.social_media_posts
        assert any("Template mode" in f for f in out.flags) and out.disclaimer


def test_education_llm_output_is_sanitised_and_flagged():
    papers, analysis, citations = approved_inputs()
    text = "Exercise reduced symptoms by 35% [S1]. Another study found a 77% drop [S4]."
    llm = FakeLLM({"education": {"title": "T", "content": text}})
    out = HealthEducationAgent(llm).run(QUESTION, Audience.patients, OutputType.public_health_article, papers, analysis, citations)
    assert out.mode == "llm"
    assert "[S4]" not in out.content and "[unverified source]" in out.content
    assert any("77" in f for f in out.flags)  # invented statistic flagged
    assert not any("35" in f for f in out.flags)  # real statistic is not
    assert out.cited_ref_ids == ["S1"]


def test_education_llm_without_citations_is_flagged_and_failure_uses_template():
    papers, analysis, citations = approved_inputs()
    uncited = FakeLLM({"education": {"title": "T", "content": "Exercise is good."}})
    out = HealthEducationAgent(uncited).run(QUESTION, Audience.general_public, OutputType.video_script, papers, analysis, citations)
    assert any("no source citations" in f for f in out.flags)
    failing = FakeLLM({"education": LLMError("rate limit")})
    out = HealthEducationAgent(failing).run(QUESTION, Audience.general_public, OutputType.video_script, papers, analysis, citations)
    assert out.mode == "template" and any("template was used" in f for f in out.flags)
