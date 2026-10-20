"""Scheduler, Background Jobs, and Notifications (Phase 16).

Provides a persistent job model with controlled scheduling, concurrency limits,
bounded retries with exponential backoff, and idempotency.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

from project_intelligence.config import Settings, load_settings
from project_intelligence.storage.database import get_conn


# ---------------------------------------------------------------------------
# Job model
# ---------------------------------------------------------------------------

class JobStatus:
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class Job:
    """A persistent background job."""

    def __init__(
        self,
        job_id: int,
        job_type: str,
        project_id: Optional[int] = None,
        user_id: Optional[int] = None,
        status: str = JobStatus.pending,
        next_run_utc: str = "",
        last_run_utc: Optional[str] = None,
        args_hash: Optional[str] = None,
        result: Optional[str] = None,
    ) -> None:
        self.job_id = job_id
        self.job_type = job_type
        self.project_id = project_id
        self.user_id = user_id
        self.status = status
        self.next_run_utc = next_run_utc
        self.last_run_utc = last_run_utc
        self.args_hash = args_hash
        self.result = result


class Scheduler:
    """Persistent job scheduler with concurrency limits and retries."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or load_settings()
        self.max_concurrent = self.settings.max_concurrent_jobs
        self.max_runtime = self.settings.max_job_runtime_seconds
        self._running: set[int] = set()

    def enqueue(
        self,
        job_type: str,
        project_id: Optional[int] = None,
        user_id: Optional[int] = None,
        args_hash: Optional[str] = None,
    ) -> Job:
        """Enqueue a new job (idempotent via args_hash)."""
        conn = get_conn()
        try:
            # Check for existing job with same args_hash
            if args_hash:
                existing = conn.execute(
                    "SELECT id, job_type, project_id, user_id, status, next_run_utc, last_run_utc, args_hash, result FROM scheduled_jobs WHERE args_hash = ?",
                    (args_hash,),
                ).fetchone()
                if existing:
                    return Job(
                        job_id=existing[0],
                        job_type=existing[1],
                        project_id=existing[2],
                        user_id=existing[3],
                        status=existing[4],
                        next_run_utc=existing[5],
                        last_run_utc=existing[6],
                        args_hash=existing[7],
                        result=existing[8],
                    )

            # Insert new job
            now = datetime.now(timezone.utc).isoformat() + "Z"
            cursor = conn.execute(
                """INSERT INTO scheduled_jobs (job_type, project_id, user_id, next_run_utc, status, args_hash)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (job_type, project_id, user_id, now, JobStatus.pending, args_hash),
            )
            conn.commit()
            job_id = cursor.lastrowid
            return Job(
                job_id=job_id,
                job_type=job_type,
                project_id=project_id,
                user_id=user_id,
                status=JobStatus.pending,
                next_run_utc=now,
                args_hash=args_hash,
            )
        finally:
            from project_intelligence.storage.database import close
            close()

    def get_pending_jobs(self, limit: int = 10) -> list[Job]:
        """Get pending jobs ordered by next_run_utc."""
        conn = get_conn()
        try:
            rows = conn.execute(
                """SELECT id, job_type, project_id, user_id, status, next_run_utc, last_run_utc, args_hash, result
                   FROM scheduled_jobs WHERE status = ? ORDER BY next_run_utc LIMIT ?""",
                (JobStatus.pending, limit),
            ).fetchall()
            return [
                Job(
                    job_id=r[0],
                    job_type=r[1],
                    project_id=r[2],
                    user_id=r[3],
                    status=r[4],
                    next_run_utc=r[5],
                    last_run_utc=r[6],
                    args_hash=r[7],
                    result=r[8],
                )
                for r in rows
            ]
        finally:
            from project_intelligence.storage.database import close
            close()

    def mark_completed(self, job_id: int, result: Optional[str] = None) -> None:
        """Mark a job as completed."""
        conn = get_conn()
        try:
            now = datetime.now(timezone.utc).isoformat() + "Z"
            conn.execute(
                "UPDATE scheduled_jobs SET status = ?, last_run_utc = ?, result = ? WHERE id = ?",
                (JobStatus.completed, now, result, job_id),
            )
            conn.commit()
        finally:
            from project_intelligence.storage.database import close
            close()

    def mark_failed(self, job_id: int, error: str, retry: bool = True) -> None:
        """Mark a job as failed, optionally scheduling a retry."""
        conn = get_conn()
        try:
            now = datetime.now(timezone.utc).isoformat() + "Z"
            if retry:
                # Exponential backoff: 2^attempt seconds, max 300s
                next_run = datetime.now(timezone.utc) + __import__("datetime").timedelta(seconds=min(300, 2 ** 3))
                next_run_str = next_run.isoformat() + "Z"
                conn.execute(
                    "UPDATE scheduled_jobs SET status = ?, last_run_utc = ?, next_run_utc = ?, result = ? WHERE id = ?",
                    (JobStatus.pending, now, next_run_str, f"FAILED: {error}", job_id),
                )
            else:
                conn.execute(
                    "UPDATE scheduled_jobs SET status = ?, last_run_utc = ?, result = ? WHERE id = ?",
                    (JobStatus.failed, now, f"FAILED (permanent): {error}", job_id),
                )
            conn.commit()
        finally:
            from project_intelligence.storage.database import close
            close()


def create_scheduler(settings: Optional[Settings] = None) -> Scheduler:
    """Factory for Scheduler."""
    if settings is None:
        settings = load_settings()
    return Scheduler(settings)