"""Storage layer for Phase 4 - SQLite persistence.

Provides the connection management, versioned migrations, and repository
data-access modules used by the Discord Project Intelligence application.
"""

from __future__ import annotations

__all__ = [
    "close",
    "get_authorized_user",
    "get_conn",
    "get_mapping",
    "get_project_by_root",
    "list_authorized_users_for_project",
    "list_evidence_for_project",
    "list_mappings_for_project",
    "list_milestones_for_project",
    "list_notes_for_project",
    "list_project_sources",
    "list_projects",
    "list_research_jobs_for_project",
    "list_research_sources",
    "list_snapshots_for_project",
    "transaction",
    "upsert_authorized_user",
    "upsert_discord_mapping",
    "upsert_evidence",
    "upsert_milestone",
    "upsert_note",
    "upsert_project",
    "upsert_project_source",
    "upsert_repository_snapshot",
    "upsert_research_job",
    "upsert_research_source",
]
