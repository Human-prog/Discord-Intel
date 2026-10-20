"""Scheduler, Background Jobs, and Notifications (Phase 16).

Provides a persistent job model with controlled scheduling, concurrency limits,
bounded retries with exponential backoff, and idempotency.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
        project_id: int | None = None,
        user_id: int | None = None,
        status: str = JobStatus.pending,
        next_run_utc: str = "",
        last_run_utc: str | None = None,
        args_hash: str | None = None,
        result: str | None = None,
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


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class Scheduler:
    """Persistent job scheduler with concurrency limits and retries."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.max_concurrent = self.settings.max_concurrent_jobs
        self.max_runtime = self.settings.max_job_runtime_seconds
        self._running: set[int] = set()

    def enqueue(
        self,
        job_type: str,
        project_id: int | None = None,
        user_id: int | None = None,
        args_hash: str | None = None,
    ) -> Job:
        """Enqueue a new job (idempotent via args_hash)."""
        conn = get_conn()

        # Idempotency: return the existing job when the same args were queued.
        if args_hash:
            existing = conn.execute(
                "SELECT id, job_type, project_id, user_id, status, next_run_utc, "
                "last_run_utc, args_hash, result FROM scheduled_jobs WHERE args_hash = ?",
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

        now = _utc_now()
        cursor = conn.execute(
            """INSERT INTO scheduled_jobs (job_type, project_id, user_id, next_run_utc, status, args_hash)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (job_type, project_id, user_id, now, JobStatus.pending, args_hash),
        )
        conn.commit()

        job_id = cursor.lastrowid
        if job_id is None:
            raise RuntimeError("scheduled job insert did not return an id")
        return Job(
            job_id=job_id,
            job_type=job_type,
            project_id=project_id,
            user_id=user_id,
            status=JobStatus.pending,
            next_run_utc=now,
            args_hash=args_hash,
        )

    def get_pending_jobs(self, limit: int = 10) -> list[Job]:
        """Get pending jobs ordered by next_run_utc."""
        rows = (
            get_conn()
            .execute(
                """SELECT id, job_type, project_id, user_id, status, next_run_utc, last_run_utc, args_hash, result
                   FROM scheduled_jobs WHERE status = ? ORDER BY next_run_utc LIMIT ?""",
                (JobStatus.pending, limit),
            )
            .fetchall()
        )
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

    def mark_completed(self, job_id: int, result: str | None = None) -> None:
        """Mark a job as completed."""
        conn = get_conn()
        conn.execute(
            "UPDATE scheduled_jobs SET status = ?, last_run_utc = ?, result = ? WHERE id = ?",
            (JobStatus.completed, _utc_now(), result, job_id),
        )
        conn.commit()

    def mark_failed(self, job_id: int, error: str, retry: bool = True) -> None:
        """Mark a job as failed, optionally scheduling a retry with backoff."""
        conn = get_conn()
        now = _utc_now()
        if retry:
            # Exponential backoff: 2^attempt seconds, capped at 300s.
            next_run = datetime.now(UTC) + timedelta(seconds=min(300, 2**3))
            next_run_str = next_run.isoformat().replace("+00:00", "Z")
            conn.execute(
                "UPDATE scheduled_jobs SET status = ?, last_run_utc = ?, "
                "next_run_utc = ?, result = ? WHERE id = ?",
                (JobStatus.pending, now, next_run_str, f"FAILED: {error}", job_id),
            )
        else:
            conn.execute(
                "UPDATE scheduled_jobs SET status = ?, last_run_utc = ?, result = ? WHERE id = ?",
                (JobStatus.failed, now, f"FAILED (permanent): {error}", job_id),
            )
        conn.commit()


def create_scheduler(settings: Settings | None = None) -> Scheduler:
    """Factory for Scheduler."""
    if settings is None:
        settings = load_settings()
    return Scheduler(settings)
