"""Storage layer for Phase 4 — SQLite persistence.

Provides the connection management, versioned migrations, and repository
data-access modules used by the Discord Project Intelligence application.
"""

from __future__ import annotations

__all__ = [
    "get_conn",
    "close",
    "transaction",
    "upsert_project",
    "get_project_by_root",
    "list_projects",
    "upsert_project_source",
    "list_project_sources",
    "upsert_discord_mapping",
    "get_mapping",
    "list_mappings_for_project",
    "upsert_authorized_user",
    "get_authorized_user",
    "list_authorized_users_for_project",
    "upsert_note",
    "list_notes_for_project",
    "upsert_milestone",
    "list_milestones_for_project",
    "upsert_evidence",
    "list_evidence_for_project",
    "upsert_repository_snapshot",
    "list_snapshots_for_project",
    "upsert_research_job",
    "list_research_jobs_for_project",
    "upsert_research_source",
    "list_research_sources",
]