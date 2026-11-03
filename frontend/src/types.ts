// These types mirror backend/app/schemas.py.

export type Audience = "general_public" | "patients" | "clinicians" | "policymakers" | "students" | "journalists";
export type OutputType = "research_summary" | "public_health_article" | "social_media_posts" | "video_script";
export type RunStatus = "queued" | "running" | "completed" | "failed";
export type StepStatus = "pending" | "running" | "completed" | "failed" | "skipped";
export type Strength = "strong" | "moderate" | "limited";
export type Support = "supported" | "partial" | "unsupported";
export type RefStatus = "verified" | "partial" | "flagged";

export interface RunRequest {
  question: string;
  audience: Audience;
  output_type: OutputType;
  max_papers: number;
}

export interface PaperLink {
  label: string;
  url: string;
}

export interface Paper {
  ref_id: string;
  title: string;
  authors: string[];
  journal: string | null;
  year: number | null;
  abstract: string;
  doi: string | null;
  pmid: string | null;
  pmcid: string | null;
  url: string | null;
  links: PaperLink[];
  sources: string[];
  pub_types: string[];
  study_design: string;
  design_inferred: boolean;
  evidence_rank: number;
  is_preprint: boolean;
  is_retracted: boolean;
  is_retraction_notice: boolean;
  cited_by_count: number | null;
  metadata_notes: string[];
}

export interface Finding {
  claim: string;
  source_ids: string[];
  strength: Strength;
  caveat: string;
}

export interface EvidenceAnalysis {
  mode: "llm" | "extractive";
  summary: string;
  findings: Finding[];
  evidence_gaps: string[];
  limitations: string[];
  conflicting_evidence: string[];
  study_design_counts: Record<string, number>;
  notes: string[];
}

export interface MetadataCheck {
  name: string;
  passed: boolean;
  severity: "info" | "warning" | "error";
  detail: string;
}

export interface ReferenceVerification {
  ref_id: string;
  title: string;
  status: RefStatus;
  cross_verified: boolean;
  checks: MetadataCheck[];
}

export interface ClaimVerification {
  index: number;
  claim: string;
  source_ids: string[];
  support: Support;
  method: "heuristic" | "llm+heuristic";
  overlap: number;
  unverified_numbers: string[];
  issues: string[];
  llm_reason: string;
}

export interface CitationReport {
  references: ReferenceVerification[];
  claims: ClaimVerification[];
  summary_issues: string[];
  flags: string[];
  counts: Record<string, number>;
  llm_used: boolean;
  notes: string[];
}

export interface EducationOutput {
  mode: "llm" | "template" | "none";
  title: string;
  content: string;
  flags: string[];
  cited_ref_ids: string[];
  disclaimer: string;
}

export interface AgentStep {
  key: string;
  name: string;
  status: StepStatus;
  message: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface LLMInfo {
  enabled: boolean;
  provider: string;
  model: string;
}

export interface ResearchRun {
  id: string;
  question: string;
  audience: Audience;
  output_type: OutputType;
  max_papers: number;
  status: RunStatus;
  error: string | null;
  created_at: string;
  updated_at: string;
  llm: LLMInfo;
  steps: AgentStep[];
  warnings: string[];
  queries: string[];
  papers: Paper[];
  analysis: EvidenceAnalysis | null;
  citations: CitationReport | null;
  output: EducationOutput | null;
}

export interface RunSummary {
  id: string;
  question: string;
  audience: Audience;
  output_type: OutputType;
  status: RunStatus;
  created_at: string;
  paper_count: number;
}

export interface Health {
  status: string;
  version: string;
  llm: LLMInfo;
  llm_problem: string | null;
  ncbi_key_configured: boolean;
  include_preprints: boolean;
  sample_question: string;
}
