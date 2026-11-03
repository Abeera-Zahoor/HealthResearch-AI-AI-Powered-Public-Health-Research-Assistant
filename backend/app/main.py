"""FastAPI application: REST API used by the React dashboard.

Start it with:  uvicorn app.main:create_app --factory --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .config import Settings, get_settings
from .db import Database
from .pipeline import Pipeline
from .schemas import ResearchRequest, ResearchRun, RunSummary

log = logging.getLogger("healthresearch")

SAMPLE_QUESTION = "Does regular physical activity reduce the risk of depression in adults?"


def create_app(settings: Optional[Settings] = None, pipeline: Optional[Pipeline] = None) -> FastAPI:
    settings = settings or get_settings()
    db = pipeline.db if pipeline else Database(settings.database_path)
    db.init()
    pipeline = pipeline or Pipeline(settings, db)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        interrupted = db.mark_interrupted()
        if interrupted:
            log.warning("Marked %s interrupted run(s) as failed.", interrupted)
        yield
        pipeline.close()

    app = FastAPI(title="HealthResearch AI", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.state.pipeline = pipeline
    app.state.db = db

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
        log.exception("Unhandled error")
        return JSONResponse(status_code=500, content={"detail": "Unexpected server error. See the backend terminal."})

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "version": __version__,
            "llm": pipeline.llm.info.model_dump(),
            "llm_problem": settings.llm_problem,
            "ncbi_key_configured": bool(settings.ncbi_api_key.strip()),
            "include_preprints": settings.include_preprints,
            "sample_question": SAMPLE_QUESTION,
        }

    @app.post("/api/research", response_model=ResearchRun, status_code=202)
    def start_research(request: ResearchRequest, background: BackgroundTasks) -> ResearchRun:
        run = pipeline.create_run(request)
        background.add_task(pipeline.execute, run.id)
        return run

    @app.get("/api/research", response_model=list[RunSummary])
    def list_research() -> list[RunSummary]:
        return db.list_runs()

    @app.get("/api/research/{run_id}", response_model=ResearchRun)
    def get_research(run_id: str) -> ResearchRun:
        run = db.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="That research run was not found.")
        return run

    @app.delete("/api/research/{run_id}", status_code=204)
    def delete_research(run_id: str) -> None:
        if not db.delete_run(run_id):
            raise HTTPException(status_code=404, detail="That research run was not found.")

    return app
