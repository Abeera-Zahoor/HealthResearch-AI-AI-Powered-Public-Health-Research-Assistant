from app.paper_utils import finalize_paper, is_valid_doi, normalize_doi
from app.schemas import Paper, ResearchRequest
from app.study_design import classify_study_design
from app.text_utils import (
    all_numbers,
    extract_citation_ids,
    extract_keywords,
    find_statistics,
    lexical_overlap,
    strip_nonclaim_numbers,
)
import pytest
from pydantic import ValidationError


def test_normalize_doi_strips_prefixes_and_case():
    assert normalize_doi("https://doi.org/10.1000/ABC.1.") == "10.1000/abc.1"
    assert normalize_doi("doi: 10.1000/xyz") == "10.1000/xyz"
    assert normalize_doi("") is None
    assert is_valid_doi("10.1000/abc") and not is_valid_doi("not-a-doi")


def test_links_are_built_only_from_identifiers():
    paper = finalize_paper(Paper(title="T", pmid="123", doi="10.1000/abc", pmcid="PMC1"))
    urls = [link.url for link in paper.links]
    assert "https://pubmed.ncbi.nlm.nih.gov/123/" in urls
    assert "https://doi.org/10.1000/abc" in urls
    assert paper.url == "https://pubmed.ncbi.nlm.nih.gov/123/"
    assert finalize_paper(Paper(title="No ids")).links == []


def test_study_design_prefers_strongest_publication_type():
    label, rank, inferred = classify_study_design(["Journal Article", "Meta-Analysis", "Review"])
    assert (label, rank, inferred) == ("Meta-analysis", 7, False)
    assert classify_study_design(["Randomized Controlled Trial"])[:2] == ("Randomized controlled trial", 6)
    label, rank, inferred = classify_study_design([], "A cohort of nurses", "")
    assert (label, inferred) == ("Cohort study", True)
    assert classify_study_design([])[0] == "Not specified"


def test_retraction_and_preprint_flags():
    retracted = finalize_paper(Paper(title="T", pmid="1", pub_types=["Retracted Publication"]))
    assert retracted.is_retracted
    notice = finalize_paper(Paper(title="T", pmid="2", pub_types=["Retraction of Publication"]))
    assert notice.is_retraction_notice and notice.evidence_rank == 1
    preprint = finalize_paper(Paper(title="T", epmc_source="PPR", epmc_id="PPR1", pub_types=["Randomized Controlled Trial"]))
    assert preprint.is_preprint and preprint.evidence_rank <= 2


def test_statistics_detection_and_normalisation():
    assert find_statistics("Scores fell by 35% and 2.5 points in 120 adults in 2021") == {"35", "2.5", "120"}
    assert "1200" in all_numbers("n = 1,200")
    assert find_statistics(strip_nonclaim_numbers("Scene 2 (0:10-0:20) lasts 30 seconds")) == set()


def test_citation_parsing_and_keywords():
    assert extract_citation_ids("Yes [S1] and also [S2, S3].") == ["S1", "S2", "S3"]
    assert extract_keywords("Does regular physical activity reduce the risk of depression in adults?") == [
        "regular", "physical", "activity", "reduce", "risk", "depression"
    ]


def test_lexical_overlap_is_high_for_same_wording_and_low_for_unrelated():
    source = "Aerobic exercise reduced depressive symptoms in adults over 12 weeks."
    assert lexical_overlap("Aerobic exercise reduced depressive symptoms in adults", source) > 0.8
    assert lexical_overlap("Vitamin supplements prevent hair loss", source) < 0.2


def test_request_validation():
    ok = ResearchRequest(question="  Does exercise help   depression?  ")
    assert ok.question == "Does exercise help depression?"
    for bad in ["short", "x" * 501, "12345 67890 !!!!", None]:
        with pytest.raises(ValidationError):
            ResearchRequest(question=bad)
    with pytest.raises(ValidationError):
        ResearchRequest(question="A valid question about health?", audience="martians")
    with pytest.raises(ValidationError):
        ResearchRequest(question="A valid question about health?", max_papers=99)
