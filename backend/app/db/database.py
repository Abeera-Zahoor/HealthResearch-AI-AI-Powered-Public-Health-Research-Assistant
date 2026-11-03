"""A tiny SQLite store. Each run is saved as one JSON document plus a few indexed columns."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Optional

from ..schemas import ResearchRun, RunSummary, utc_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          TEXT PRIMARY KEY,
    question    TEXT NOT NULL,
    audience    TEXT NOT NULL,
    output_type TEXT NOT NULL,
    status      TEXT NOT NULL,
    paper_count INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    data        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs (created_at DESC);
"""


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.DatabaseError:  # pragma: no cover - e.g. network drives
                pass
            conn.executescript(SCHEMA)

    def save_run(self, run: ResearchRun) -> None:
        run.updated_at = utc_now()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                INSERT INTO runs (id, question, audience, output_type, status, paper_count,
                                  created_at, updated_at, data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    paper_count = excluded.paper_count,
                    updated_at = excluded.updated_at,
                    data = excluded.data
                """,
                (
                    run.id,
                    run.question,
                    run.audience.value,
                    run.output_type.value,
                    run.status,
                    len(run.papers),
                    run.created_at,
                    run.updated_at,
                    run.model_dump_json(),
                ),
            )

    def get_run(self, run_id: str) -> Optional[ResearchRun]:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT data FROM runs WHERE id = ?", (run_id,)).fetchone()
        return ResearchRun.model_validate_json(row["data"]) if row else None

    def list_runs(self, limit: int = 100) -> list[RunSummary]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT id, question, audience, output_type, status, paper_count, created_at "
                "FROM runs ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [RunSummary(**dict(row)) for row in rows]

    def delete_run(self, run_id: str) -> bool:
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        return cursor.rowcount > 0

    def mark_interrupted(self) -> int:
        """Runs still 'queued'/'running' at startup were cut off by a server restart."""
        count = 0
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT id FROM runs WHERE status IN ('queued', 'running')").fetchall()
        for row in rows:
            run = self.get_run(row["id"])
            if run is None:
                continue
            run.status = "failed"
            run.error = "This run was interrupted because the server restarted. Please run it again."
            for step in run.steps:
                if step.status in ("pending", "running"):
                    step.status = "failed" if step.status == "running" else "skipped"
            self.save_run(run)
            count += 1
        return count
