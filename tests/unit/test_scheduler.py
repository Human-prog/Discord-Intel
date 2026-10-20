"""Scheduler and background job tests (Phase 16)."""

from __future__ import annotations

import pytest

from project_intelligence.jobs.scheduler import JobStatus, Scheduler, create_scheduler


@pytest.fixture()
def scheduler(app_settings) -> Scheduler:
    return Scheduler(app_settings)


def _row(db, job_id: int):
    return db.execute(
        "SELECT status, next_run_utc, last_run_utc, result FROM scheduled_jobs WHERE id = ?",
        (job_id,),
    ).fetchone()


def test_enqueue_creates_pending_job(scheduler, db) -> None:
    job = scheduler.enqueue("health_check", project_id=None, user_id=123)
    assert job.job_id > 0
    assert job.status == JobStatus.pending
    assert job.next_run_utc.endswith("Z")

    row = _row(db, job.job_id)
    assert row[0] == JobStatus.pending
    assert row[1].endswith("Z")


def test_enqueue_is_idempotent_by_args_hash(scheduler, db) -> None:
    first = scheduler.enqueue("research", project_id=1, user_id=123, args_hash="hash-1")
    second = scheduler.enqueue("research", project_id=1, user_id=123, args_hash="hash-1")

    assert second.job_id == first.job_id
    count = db.execute("SELECT COUNT(*) FROM scheduled_jobs").fetchone()[0]
    assert count == 1


def test_enqueue_without_args_hash_always_inserts(scheduler, db) -> None:
    scheduler.enqueue("health_check")
    scheduler.enqueue("health_check")
    assert db.execute("SELECT COUNT(*) FROM scheduled_jobs").fetchone()[0] == 2


def test_pending_jobs_are_listed(scheduler) -> None:
    first = scheduler.enqueue("health_check")
    second = scheduler.enqueue("research")

    pending = scheduler.get_pending_jobs()
    assert {job.job_id for job in pending} == {first.job_id, second.job_id}
    assert all(job.status == JobStatus.pending for job in pending)


def test_pending_jobs_respect_limit(scheduler) -> None:
    for _ in range(3):
        scheduler.enqueue("health_check")
    assert len(scheduler.get_pending_jobs(limit=2)) == 2


def test_completed_jobs_leave_the_pending_queue(scheduler, db) -> None:
    job = scheduler.enqueue("health_check")
    scheduler.mark_completed(job.job_id, result="ok")

    assert scheduler.get_pending_jobs() == []
    row = _row(db, job.job_id)
    assert row[0] == JobStatus.completed
    assert row[2].endswith("Z")
    assert row[3] == "ok"


def test_failed_job_with_retry_returns_to_pending(scheduler, db) -> None:
    job = scheduler.enqueue("health_check")
    scheduler.mark_failed(job.job_id, "boom", retry=True)

    row = _row(db, job.job_id)
    assert row[0] == JobStatus.pending
    assert row[3].startswith("FAILED: boom")
    # The retry is scheduled in the future but still imminent (capped backoff).
    assert row[1].endswith("Z")


def test_failed_job_without_retry_is_terminal(scheduler, db) -> None:
    job = scheduler.enqueue("health_check")
    scheduler.mark_failed(job.job_id, "boom", retry=False)

    row = _row(db, job.job_id)
    assert row[0] == JobStatus.failed
    assert row[3] == "FAILED (permanent): boom"


def test_factory_returns_scheduler(app_settings) -> None:
    scheduler = create_scheduler(app_settings)
    assert isinstance(scheduler, Scheduler)
    assert scheduler.max_concurrent == app_settings.max_concurrent_jobs
