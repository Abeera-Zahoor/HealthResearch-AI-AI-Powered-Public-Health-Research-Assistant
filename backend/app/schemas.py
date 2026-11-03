"""Pydantic models shared by the agents, the database and the REST API."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Audience(str, Enum):
    general_public = "general_public"
    patients = "patients"
    clinicians = "clinicians"
    policymakers = "policymakers"
    students = "students"
    journalists = "journalists"


class OutputType(str, Enum):
    research_summary = "research_summary"
    public_health_article = "public_health_article"
    social_media_posts = "social_media_posts"
    video_script = "video_script"


AUDIENCE_LABELS = {
    Audience.general_public: "General public",
    Audience.patients: "Patients and caregivers",
    Audience.clinicians: "Healthcare professionals",
    Audience.policymakers: "Policymakers",
    Audience.students: "Students",
    Audience.journalists: "Journalists",
}

OUTPUT_LABELS = {
    OutputType.research_summary: "Research summary",
    OutputType.public_health_article: "Public health article",
    OutputType.social_media_posts: "Social media posts",
    OutputType.video_script: "Short video script",
}


# ----------------------------------------------------------------------
# Request
# ----------------------------------------------------------------------
class ResearchRequest(BaseModel):
    question: str
    audience: Audience = Audience.general_public
    output_type: OutputType = OutputType.research_summary
    max_papers: Optional[int] = Field(default=None, ge=3, le=20)

    @field_validator("question", mode="before")
    @classmethod
    def _clean_question(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("Please enter your research question as text.")
        text = " ".join(value.split())
        if len(text) < 10:
            raise ValueError("Please enter a research question of at least 10 characters.")
        if len(text) > 500:
            raise ValueError("Please keep the research question under 500 characters.")
        if not re.search(r"[A-Za-z]{3,}", text):
            raise ValueError("The research question must contain words, not just symbols or numbers.")
        return text


# ----------------------------------------------------------------------
# Papers
# ----------------------------------------------------------------------
class Link(BaseModel):
    label: str
    url: str


class Paper(BaseModel):
    ref_id: str = ""
    title: str
    authors: list[str] = Field(default_factory=list)
    journal: Optional[str] = None
    year: Optional[int] = None
    abstract: str = ""
    doi: Optional[str] = None
    pmid: Optional[str] = None
    pmcid: Optional[str] = None
    epmc_source: Optional[str] = None
    epmc_id: Optional[str] = None
    url: Optional[str] = None
    links: list[Link] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    pub_types: list[str] = Field(default_factory=list)
    study_design: str = "Not specified"
    design_inferred: bool = False
    evidence_rank: int = 2
    is_preprint: bool = False
    is_retracted: bool = False
    is_retraction_notice: bool = False
    cited_by_count: Optional[int] = None
    metadata_notes: list[str] = Field(default_factory=list)

    @property
    def has_abstract(self) -> bool:
        return len(self.abstract.strip()) >= 40


# ----------------------------------------------------------------------
# Evidence analysis
# ----------------------------------------------------------------------
Strength = Literal["strong", "moderate", "limited"]


class Finding(BaseModel):
    claim: str
    source_ids: list[str] = Field(default_factory=list)
    strength: Strength = "limited"
    caveat: str = ""


class EvidenceAnalysis(BaseModel):
    mode: Literal["llm", "extractive"] = "extractive"
    summary: str = ""
    findings: list[Finding] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    conflicting_evidence: list[str] = Field(default_factory=list)
    study_design_counts: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


# ----------------------------------------------------------------------
# Citation verification
# ----------------------------------------------------------------------
class MetadataCheck(BaseModel):
    name: str
    passed: bool
    severity: Literal["info", "warning", "error"] = "info"
    detail: str = ""


class ReferenceVerification(BaseModel):
    ref_id: str
    title: str
    status: Literal["verified", "partial", "flagged"]
    cross_verified: bool = False
    checks: list[MetadataCheck] = Field(default_factory=list)


Support = Literal["supported", "partial", "unsupported"]


class ClaimVerification(BaseModel):
    index: int
    claim: str
    source_ids: list[str] = Field(default_factory=list)
    support: Support
    method: Literal["heuristic", "llm+heuristic"] = "heuristic"
    overlap: float = 0.0
    unverified_numbers: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    llm_reason: str = ""


class CitationReport(BaseModel):
    references: list[ReferenceVerification] = Field(default_factory=list)
    claims: list[ClaimVerification] = Field(default_factory=list)
    summary_issues: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    llm_used: bool = False
    notes: list[str] = Field(default_factory=list)


# ----------------------------------------------------------------------
# Final output
# ----------------------------------------------------------------------
class EducationOutput(BaseModel):
    mode: Literal["llm", "template", "none"] = "none"
    title: str = ""
    content: str = ""
    flags: list[str] = Field(default_factory=list)
    cited_ref_ids: list[str] = Field(default_factory=list)
    disclaimer: str = ""


# ----------------------------------------------------------------------
# Run (one full workflow execution)
# ----------------------------------------------------------------------
StepStatus = Literal["pending", "running", "completed", "failed", "skipped"]
RunStatus = Literal["queued", "running", "completed", "failed"]


class AgentStep(BaseModel):
    key: str
    name: str
    status: StepStatus = "pending"
    message: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class LLMInfo(BaseModel):
    enabled: bool
    provider: str
    model: str = ""


class ResearchRun(BaseModel):
    id: str
    question: str
    audience: Audience
    output_type: OutputType
    max_papers: int = 10
    status: RunStatus = "queued"
    error: Optional[str] = None
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    llm: LLMInfo = Field(default_factory=lambda: LLMInfo(enabled=False, provider="none"))
    steps: list[AgentStep] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    papers: list[Paper] = Field(default_factory=list)
    analysis: Optional[EvidenceAnalysis] = None
    citations: Optional[CitationReport] = None
    output: Optional[EducationOutput] = None


class RunSummary(BaseModel):
    id: str
    question: str
    audience: Audience
    output_type: OutputType
    status: RunStatus
    created_at: str
    paper_count: int = 0
