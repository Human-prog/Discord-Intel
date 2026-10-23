"""Project catalog, work history, and research provenance (Phase 16).

Adds the fields needed to hold an imported catalog of every project on the
owner's workstation, the work items derived from each project (Git commits,
notes, and manual entries), and the extra provenance fields required by real
local/web research jobs.

The migration is deliberately idempotent: every column, index, and table is
created only when it is missing.  That keeps a partially-applied migration
recoverable without hand-editing the database.
"""

from __future__ import annotations

from typing import Any


def _columns(conn: Any, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_column(conn: Any, table: str, column: str, definition: str) -> None:
    if column not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def up(conn: Any) -> None:
    """Apply the catalog/work/research schema additions."""
    conn.execute("BEGIN")

    # ---- projects: catalog metadata -------------------------------------
    _add_column(conn, "projects", "catalog_key", "TEXT")
    _add_column(conn, "projects", "catalog_status", "TEXT NOT NULL DEFAULT 'unknown'")
    _add_column(conn, "projects", "category", "TEXT")
    _add_column(conn, "projects", "priority", "TEXT")
    _add_column(conn, "projects", "tech_stack_json", "TEXT")
    _add_column(conn, "projects", "repo_url", "TEXT")
    _add_column(conn, "projects", "local_path", "TEXT")
    _add_column(conn, "projects", "last_activity_utc", "TEXT")
    _add_column(conn, "projects", "source", "TEXT NOT NULL DEFAULT 'manual'")
    _add_column(conn, "projects", "monitored", "INTEGER NOT NULL DEFAULT 1")
    _add_column(conn, "projects", "metadata_json", "TEXT")

    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_projects_catalog_key ON projects(catalog_key)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_source ON projects(source)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_priority ON projects(priority)")

    # ---- work_items ------------------------------------------------------
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS work_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            work_type TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT,
            status TEXT NOT NULL DEFAULT 'done',
            source TEXT NOT NULL,
            external_id TEXT,
            occurred_at_utc TEXT,
            created_at_utc TEXT NOT NULL,
            metadata_json TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_work_items_external "
        "ON work_items(project_id, source, external_id)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_work_items_project ON work_items(project_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_work_items_occurred ON work_items(occurred_at_utc)"
    )

    # ---- catalog imports -------------------------------------------------
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            source_checksum TEXT NOT NULL UNIQUE,
            imported_at_utc TEXT NOT NULL,
            project_count INTEGER NOT NULL DEFAULT 0,
            work_item_count INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT
        )
        """
    )

    # ---- research jobs: repeated questions are allowed ------------------
    conn.execute("DROP INDEX IF EXISTS uq_research_jobs_question")
    _add_column(conn, "research_jobs", "scope", "TEXT NOT NULL DEFAULT 'web'")
    _add_column(conn, "research_jobs", "provider", "TEXT")
    _add_column(conn, "research_jobs", "error_text", "TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_research_jobs_started ON research_jobs(started_at_utc)"
    )

    # ---- research sources: citation text and local references -----------
    _add_column(conn, "research_sources", "snippet", "TEXT")
    _add_column(conn, "research_sources", "relevance_score", "REAL NOT NULL DEFAULT 0.0")
    _add_column(conn, "research_sources", "source_ref", "TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_research_sources_job ON research_sources(research_job_id)"
    )

    # ---- research reports: one report per job ---------------------------
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_research_reports_job "
        "ON research_reports(research_job_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_research_reports_generated "
        "ON research_reports(generated_at_utc)"
    )

    conn.execute("COMMIT")
