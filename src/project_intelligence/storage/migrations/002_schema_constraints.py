"""Schema constraint fixes for the repository UPSERT layer.

SQLite cannot add table constraints in place, but a unique index satisfies an
``ON CONFLICT`` target just the same.  Every statement is idempotent, so this
migration is safe on fresh databases (where the initial migration already
declares some of these constraints) and on databases created before the
constraints existed.

Note: a unique index treats NULL values as distinct, so evidence rows with a
NULL ``source_id`` are intentionally not deduplicated by title.
"""

from typing import Any


def up(conn: Any) -> None:
    """Create the unique indexes required by repository UPSERT statements."""
    statements = (
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_repository_snapshots_commit "
        "ON repository_snapshots(project_id, git_commit_hash)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_research_jobs_question "
        "ON research_jobs(project_id, question)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_research_sources_title "
        "ON research_sources(research_job_id, title)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_milestones_title ON milestones(project_id, title)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_source_title "
        "ON evidence(project_id, source_id, title)",
    )
    for statement in statements:
        conn.execute(statement)
    conn.commit()
