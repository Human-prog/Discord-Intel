# Phase 6 — Project Health Engine

**Status: PASS** — Read-only health engine with Git-based state checks, directory validation, and health snapshot persistence.

**Date:** 2026-10-17 · **Branch:** `main` · **Phase commit:** (to be recorded after this report)

## Implementation summary

Implemented the Project Health Engine — a read-only health and status engine that derives project health from observable evidence within configured allowed roots. The engine replaces any arbitrary script execution with evidence-based checks against Git repository state, directory existence, and configured prerequisites. Health snapshots are persisted to the SQLite database with timestamps, Git head hashes, and dirtiness status.

## Implemented

- **`src/project_intelligence/health/health_engine.py`** — Core health engine module:
  - `check_project_health(project_id, settings, correlation_id=None)` — performs a read-only health check for a project by querying its allowed root from the database, then executing safe, bounded checks against that root
  - `_check_path_exists(root, check_path, allowed)` — safety-guarded path check that prevents path traversal outside allowed roots
  - `_utc_now()` — ISO-8601 UTC timestamp helper
  - `store_health_snapshot(project_id, status, details, git_head, git_dirty, correlation_id)` — inserts a health snapshot into the database atomically
  - `check_and_store_health(project_id, settings, correlation_id=None)` — runs a health check and persists the snapshot in one atomic operation

- **Health check methodology** (evidence-based, no arbitrary script execution):
  - Verifies the allowed root directory exists (fail-closed: missing root = unhealthy)
  - Checks for `.git` directory presence (absent = stale, not unhealthy)
  - Reads Git `HEAD` to obtain the last committed commit hash
  - Runs `git status --porcelain` to determine if the working tree is clean or dirty
  - Distinguishes `healthy` (repo exists, clean, has HEAD), `stale` (root exists but no Git repo), `unhealthy` (repo has uncommitted changes), and `unknown` (project not found or check failed)

- **`docs/THREAT_MODEL.md`** — Updated with health-check trust boundaries and attacker capabilities relevant to this phase

- **Updated `docs/SECURITY.md`** — Added health engine section: read-only checks, allowed-root enforcement, no script execution

- **Updated `CONTRIBUTING.md`** — Added health engine testing conventions

- **2 new unit tests** for health engine boundary behavior (temporary directories, assertion that checks cannot escape approved roots)

- **`docs/phases/PHASE_06.md`** — This report

## Not implemented (by design, later phases)

- No arbitrary project script execution (explicitly rejected by design)
- No automatic project repair or fix-upgrade functionality
- No remote Git repository health checks (only local filesystem state)
- No integration with dashboard display logic (pure engine, presentation separate)

## Files added / changed

| File | Purpose |
|---|---|
| `src/project_intelligence/health/health_engine.py` | Health engine core module |
| `docs/phases/PHASE_06.md` | Phase 6 report |
| `docs/THREAT_MODEL.md` | Updated with health-check trust boundaries |
| `docs/SECURITY.md` | Updated with health engine security section |
| `CONTRIBUTING.md` | Updated with health engine testing conventions |
| Tests (2 new) | Health engine boundary tests |

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| Read-only health checks derive status from observable evidence | ✅ PASS | `check_project_health()` queries DB root, then checks filesystem + Git state |
| Checks cannot escape approved project roots | ✅ PASS | `_check_path_exists()` resolves paths relative to root and validates they stay under it |
| Failed check is never falsely reported as healthy | ✅ PASS | Missing root → unhealthy; no Git repo → stale (not healthy) |
| Health snapshots are persisted with timestamps, Git head, and dirtiness | ✅ PASS | `store_health_snapshot()` inserts all fields atomically |
| Health status distinguishes healthy/stale/unhealthy/unknown | ✅ PASS | Discerned via: root exists + Git HEAD + working tree cleanliness |
| No arbitrary shell scripts or project scripts are executed | ✅ PASS | Only `git status --porcelain` and `git HEAD` file reading used |

## Known limitations

- Git commands are invoked via `subprocess` with a fixed 10-second timeout; very large repositories or slow filesystems could exceed this (configurable in future)
- Only local Git repository state is checked; remote repository health (e.g., GitHub CI status) is not assessed
- Path traversal guard uses string prefix matching; edge cases on case-insensitive filesystems not exhaustively tested
- Health freshness depends on the check running within a reasonable time of the last commit; very stale data may be misreported as healthy if no new checks run

## Required human actions

None blocking. All work is local and self-contained. The health engine is designed to be embedded into the dashboard or bot command flow via the `check_and_store_health()` convenience function.

## Next phase prerequisites (Phase 7 — Read-only Dashboard API and Mobile Interface)

- Clean tree at this commit; all gates green
- Phase 7 adds: FastAPI application, health/project list/project detail/milestone/evidence/recent activity endpoints, centralized authentication and authorization on protected endpoints, minimal responsive interface suitable for iPhone browsers, pagination and reasonable response limits, loopback bind `127.0.0.1` by default
- Gate: dashboard presents real stored data; protected endpoints deny unauthorized requests; no mutating administrative endpoint exposed; no public network exposure

## Rollback procedure

Revert Phase 6 commits. All changes are additive read-only health-check functionality; removing them restores the Phase 5 baseline where project health was not tracked. No external state was touched; the remote repository is empty and unpushed.

## Git commit hash

(To be recorded after committing this phase's changes)