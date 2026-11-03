"""The workflow that connects the four agents and records progress in the database."""
from __future__ import annotations

import logging
import uuid

import httpx

from .agents import (
    AgentError,
    CitationVerificationAgent,
    EvidenceAnalysisAgent,
    HealthEducationAgent,
    ResearchAgent,
)
from .apis import EuropePMCClient, PubMedClient, build_http_client
from .config import Settings
from .db import Database
from .llm import LLMClient
from .schemas import AgentStep, OUTPUT_LABELS, ResearchRequest, ResearchRun, utc_now

log = logging.getLogger("healthresearch")

STEP_DEFS = [
    ("research", "Research Agent"),
    ("analysis", "Evidence Analysis Agent"),
    ("verification", "Citation Verification Agent"),
    ("education", "Health Education Agent"),
]


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        http: httpx.Client | None = None,
        pubmed: PubMedClient | None = None,
        europepmc: EuropePMCClient | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        self.settings = settings
        self.db = db
        self._owns_http = http is None and (pubmed is None or europepmc is None)
        self.http = http or (build_http_client(settings.http_timeout_seconds) if self._owns_http else None)
        self.pubmed = pubmed or PubMedClient(
            self.http, settings.pubmed_base_url, settings.ncbi_api_key, settings.ncbi_email  # type: ignore[arg-type]
        )
        self.europepmc = europepmc or EuropePMCClient(self.http, settings.europepmc_base_url)  # type: ignore[arg-type]
        self.llm = llm or LLMClient(settings)

        self.research = ResearchAgent(self.pubmed, self.europepmc, self.llm, settings.include_preprints)
        self.analysis = EvidenceAnalysisAgent(self.llm)
        self.verification = CitationVerificationAgent(self.pubmed, self.europepmc, self.llm)
        self.education = HealthEducationAgent(self.llm)

    def close(self) -> None:
        if self._owns_http and self.http is not None:
            self.http.close()

    # ------------------------------------------------------------------
    def create_run(self, request: ResearchRequest) -> ResearchRun:
        run = ResearchRun(
            id=uuid.uuid4().hex[:12],
            question=request.question,
            audience=request.audience,
            output_type=request.output_type,
            max_papers=request.max_papers or self.settings.default_max_papers,
            llm=self.llm.info,
            steps=[AgentStep(key=k, name=n) for k, n in STEP_DEFS],
        )
        if self.settings.llm_problem:
            run.warnings.append(f"AI writing is disabled: {self.settings.llm_problem} Running in extractive/template mode.")
        self.db.save_run(run)
        return run

    # ------------------------------------------------------------------
    def _step(self, run: ResearchRun, key: str) -> AgentStep:
        return next(s for s in run.steps if s.key == key)

    def _begin(self, run: ResearchRun, key: str, message: str = "Working...") -> None:
        step = self._step(run, key)
        step.status, step.message, step.started_at = "running", message, utc_now()
        self.db.save_run(run)

    def _end(self, run: ResearchRun, key: str, status: str, message: str) -> None:
        step = self._step(run, key)
        step.status, step.message, step.finished_at = status, message, utc_now()  # type: ignore[assignment]
        self.db.save_run(run)

    def _skip_rest(self, run: ResearchRun, reason: str) -> None:
        for step in run.steps:
            if step.status == "pending":
                step.status, step.message = "skipped", reason

    def _fail(self, run: ResearchRun, key: str, message: str) -> None:
        self._end(run, key, "failed", message)
        run.status, run.error = "failed", message
        self._skip_rest(run, "Skipped because an earlier agent failed.")
        self.db.save_run(run)

    # ------------------------------------------------------------------
    def execute(self, run_id: str) -> None:
        """Run the whole workflow. Never raises: problems are stored on the run."""
        run = self.db.get_run(run_id)
        if run is None:
            return
        try:
            self._execute(run)
        except Exception as exc:  # pragma: no cover - safety net for unexpected bugs
            log.exception("Run %s crashed", run_id)
            run.status = "failed"
            run.error = f"Unexpected error: {type(exc).__name__}. See the backend terminal for details."
            for step in run.steps:
                if step.status == "running":
                    step.status, step.message = "failed", run.error
                elif step.status == "pending":
                    step.status, step.message = "skipped", "Skipped because of an error."
            self.db.save_run(run)

    def _execute(self, run: ResearchRun) -> None:
        run.status = "running"
        self.db.save_run(run)

        # 1. Research --------------------------------------------------
        self._begin(run, "research", "Searching PubMed and Europe PMC...")
        try:
            outcome = self.research.run(run.question, run.max_papers)
        except AgentError as exc:
            return self._fail(run, "research", str(exc))
        run.queries, run.papers = outcome.queries, outcome.papers
        run.warnings.extend(outcome.warnings)
        if not run.papers:
            run.warnings.append("No papers were found. Try rewording the question with more common medical terms.")
            self._end(run, "research", "completed", "No papers found.")
            self._skip_rest(run, "Skipped because no papers were found.")
            run.status = "completed"
            self.db.save_run(run)
            return
        self._end(run, "research", "completed", f"Retrieved {len(run.papers)} real paper(s) using {len(run.queries)} search quer{'y' if len(run.queries) == 1 else 'ies'}.")

        # 2. Evidence analysis -----------------------------------------
        self._begin(run, "analysis", "Analysing abstracts...")
        try:
            run.analysis = self.analysis.run(run.question, run.papers)
        except AgentError as exc:
            return self._fail(run, "analysis", str(exc))
        run.warnings.extend(n for n in run.analysis.notes if "failed" in n)
        self._end(run, "analysis", "completed", f"{len(run.analysis.findings)} finding(s), {len(run.analysis.evidence_gaps)} gap(s) identified ({run.analysis.mode} mode).")

        # 3. Citation verification -------------------------------------
        self._begin(run, "verification", "Checking references and claims...")
        try:
            run.citations = self.verification.run(run.papers, run.analysis)
        except AgentError as exc:
            return self._fail(run, "verification", str(exc))
        c = run.citations.counts
        self._end(
            run,
            "verification",
            "completed",
            f"References: {c['references_verified']} verified, {c['references_partial']} partial, {c['references_flagged']} flagged. "
            f"Claims: {c['claims_supported']} supported, {c['claims_partial']} partial, {c['claims_unsupported']} unsupported.",
        )

        # 4. Health education ------------------------------------------
        self._begin(run, "education", f"Writing {OUTPUT_LABELS[run.output_type].lower()}...")
        try:
            run.output = self.education.run(
                run.question, run.audience, run.output_type, run.papers, run.analysis, run.citations
            )
        except AgentError as exc:
            return self._fail(run, "education", str(exc))
        if run.output.mode == "none":
            self._end(run, "education", "completed", "No content generated: no finding passed verification.")
            run.warnings.append("No finding passed verification, so no educational content was produced.")
        else:
            self._end(run, "education", "completed", f"{OUTPUT_LABELS[run.output_type]} written ({run.output.mode} mode), {len(run.output.flags)} flag(s).")

        run.status = "completed"
        self.db.save_run(run)
