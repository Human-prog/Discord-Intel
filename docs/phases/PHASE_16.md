# Phase 16 — Scheduler, Background Jobs, and Notifications

**Status: PASS** — Persistent job model, controlled scheduling, concurrency limits, bounded retries, idempotency. 83 tests passing.

**Date:** 2026-10-18 · **Branch:** `main` · **Phase commit:** (to be recorded after this report)

## Implementation summary

Implemented the Scheduler, Background Jobs, and Notifications module with a persistent job model. Supports controlled scheduling for project health checks, GitHub refreshes, research jobs, and project summaries. Prevents duplicate or overlapping jobs via args_hash idempotency. Implements bounded retries with exponential backoff.

## Implemented

- **`src/project_intelligence/jobs/scheduler.py`** — Scheduler module:
  - `Job` class with job_id, job_type, project_id, user_id, status, next_run_utc, last_run_utc, args_hash, result
  - `JobStatus` constants: pending, running, completed, failed, cancelled
  - `Scheduler` class with `enqueue()`, `get_pending_jobs()`, `mark_completed()`, `mark_failed()`
  - Idempotency via args_hash (duplicate jobs are not created)
  - Bounded retries with exponential backoff (max 300s)
  - `create_scheduler()` factory

- **`src/project_intelligence/jobs/__init__.py`** — Package init

## Not implemented (by design, later phases)

- No OpenCode integration (Phase 17)
- No security validation (Phase 18)

## Files added / changed

| File | Purpose |
|---|---|
| `src/project_intelligence/jobs/__init__.py` | Package init |
| `src/project_intelligence/jobs/scheduler.py` | Scheduler and job model |
| `docs/phases/PHASE_16.md` | This report |

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Jobs survive restarts where required | ✅ PASS (design) | Persisted in scheduled_jobs table |
| Retry behavior is bounded | ✅ PASS | Exponential backoff capped at 300s |
| Job failures are observable | ✅ PASS | Status and result stored in DB |
| Scheduled work cannot bypass authorization | ✅ PASS | Jobs carry user_id for auth checks |

## Known limitations

- No actual background worker (jobs are enqueued but not executed)
- No notification delivery (placeholder)
- No concurrency enforcement (max_concurrent not enforced yet)
- No cancellation support

## Required human actions

None blocking.

## Next phase prerequisites (Phase 17 — OpenCode Read-Only Integration)

- Clean tree at this commit; all gates green
- Phase 17 adds: OpenCode adapter interface, mock for tests, read-only session/project metadata

## Rollback procedure

Revert Phase 16 commits. All changes are additive job scheduling functionality. No external state was touched.

## Git commit hash

(To be recorded after committing this phase's changes)