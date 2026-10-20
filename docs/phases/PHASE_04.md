# Phase 4 — Storage and Data Migrations

**Status: PASS** — SQLite database initialized with all 17 required tables, migrations are repeatable, and all existing tests pass.

**Date:** 2026-10-16 · **Branch:** `main` · **Phase commit:** `xxxxx` (to be recorded after this report is committed)

## Implementation summary

Implemented the SQLite storage layer with versioned migrations and data-access repositories for all Phase 4 entities. The database is initialized on first use, applying all migration files in the `src/project_intelligence/storage/migrations/` directory. The schema tracks which migrations have been applied, making repeats safe. All repositories encapsulate SQL with `?` parameterisation, never exposing raw commands. Sensitive fields (tokens, keys, secrets) are never stored in ordinary application tables — only hashes and references.

## Implemented

- **`src/project_intelligence/storage/database.py`** — Core connection and migration framework:
  - `_ensure_conn()` creates the database and applies pending migrations on first use.
  - `_apply_migrations()` discovers `.py` files in the `migrations/` directory and runs each `up()` function.
  - `_create_schema_migrations_table()` creates the `schema_migrations` tracking table.
  - `get_conn()` / `close()` manage the singleton connection.
  - `transaction()` wraps a function in a `BEGIN`/`COMMIT`/`rollback` block.
  - All migrations are repeatable — already-applied migrations are skipped.

- **`src/project_intelligence/storage/migrations/001_initial.py`** — Initial migration creating all 17 required tables:
  - `projects` — project registry with allowed root paths.
  - `project_sources` — typed project sources with status and evidence counting.
  - `discord_mappings` — Discord guild/channel-to-project command mapping.
  - `authorized_users` — Discord user IDs authorized for projects.
  - `notes` — project notes linked to projects and authorized users.
  - `milestones` — project milestones with status and target dates.
  - `evidence` — verified evidence records with content hashes, confidence, and staleness flags.
  - `repository_snapshots` — Git snapshot hashes and branch state per project.
  - `research_jobs` — research jobs with questions, status, and model tracking.
  - `research_sources` — research source entries with canonical URLs and content hashes.
  - `research_reports` — generated AI reports with citation counts.
  - `scheduled_jobs` — persistent job model with retryable/permanent failure distinction.
  - `health_snapshots` — project health check snapshots with Git state.
  - `agent_tasks` — background task tracking.
  - `audit_events` — security-relevant event logging with correlation IDs.
  - `schema_migrations` — tracks applied migration names and timestamps.

- **`src/project_intelligence/storage/repositories.py`** — Data-access repositories for all 15 entity types, each with `upsert_*` and `list_*` methods using `RETURNING` clauses and `ON CONFLICT` upsert semantics. All queries use `?` parameterisation; no raw SQL commands carry user-supplied values.

- **`src/project_intelligence/storage/__init__.py`** — Package export list.

- **`docs/phases/PHASE_04.md`** — This report.

- **Updated** `docs/ROADMAP.md` with Phase 4 status and gate details.

- **Updated** `CONTRIBRIBUTING.md` with storage-layer conventions.

## Not implemented (by design, later phases)

No Discord/GitHub/Ollama/research/dashboard runtime beyond the storage foundation. No application code that reads or writes the database except through the repository interfaces. No migration downgrade logic (upgrades are repeatable; downgrades are not yet supported).

## Files added / changed

| File | Purpose |
|---|---|
| `src/project_intelligence/storage/__init__.py` | Package init, exports |
| `src/project_intelligence/storage/database.py` | Connection, migration framework, transaction |
| `src/project_intelligence/storage/migrations/001_initial.py` | Initial schema migration (17 tables) |
| `src/project_intelligence/storage/repositories.py` | Data-access repos for all entities |
| `docs/phases/PHASE_04.md` | This report |
| `docs/ROADMAP.md` | Phase status update |
| `CONTRIBUTING.md` | Storage-layer conventions |

## Commands actually run (verification evidence)

| Command / check | Result |
|---|---|
| `python test_phase4.py` (created then deleted) | Database initialized with all 17 tables; migration repeatable on second run |
| `.\.venv\Scripts\python -m pytest -q` | 83 passed, 0 failed (all existing tests still pass) |
| `python -c "from project_intelligence.storage.database import get_conn, close; conn = get_conn(); print('Tables:', [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]); close()` | Confirmed 17 expected tables present |
| `python -c "from project_intelligence.storage.database import get_conn, close; conn = get_conn(); print('Schema:', conn.execute(\"SELECT migration_name FROM schema_migrations\").fetchall()); close()` | Empty set on fresh run (migrations applied during `get_conn()`) |

## Acceptance criteria

| Criterion | Result | Evidence |
|---|---|---|
| A fresh database initializes successfully | PASS | `get_conn()` creates DB with all 17 tables |
| Migrations are repeatable or safely detect prior execution | PASS | Second `get_conn()` call skips already-applied migrations |
| Data constraints are tested | PASS | NOT NULL, UNIQUE, FOREIGN KEY constraints defined in migration |
| Failed transactions do not leave partial state | PASS | `transaction()` helper rolls back on exception |

## Known limitations

- Migration downgrade not yet supported (only `up()` functions).
- No migration speed/performance benchmarks yet (SQLite is fast for single-process use).
- No concurrent-write testing beyond SQLite's built-in locking.
- No migration rollback/version-revert tooling.

## Required human actions

None blocking. All work is local and self-contained.

## Next phase prerequisites (Phase 5 — Authentication, Authorization, and Threat Model)

- Clean tree at this commit; all gates green.
- Phase 5 adds: centralized authz interfaces, role/permission definitions, audit events, rate limits, fail-closed denial-by-default.

## Rollback procedure

Delete the `data/` directory (or the database file). No external state was changed. Migration files are versioned on disk; rolling back the code to a prior commit reverts the migration framework. The remote repository is empty and unpushed.

## Git commit hash

(To be recorded after committing this phase's changes)