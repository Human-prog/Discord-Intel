"""Storage layer for Phase 4 - SQLite persistence.

Provides the connection management, versioned migrations, and repository
data-access modules used by the Discord Project Intelligence application.
"""

from __future__ import annotations

__all__ = [
    "close",
    "complete_research_job",
    "count_work_items",
    "get_authorized_user",
    "get_catalog_import",
    "get_conn",
    "get_mapping",
    "get_project_by_catalog_key",
    "get_project_by_id",
    "get_project_by_root",
    "get_research_job",
    "get_research_report",
    "list_authorized_users_for_project",
    "list_evidence_for_project",
    "list_mappings_for_project",
    "list_milestones_for_project",
    "list_notes_for_project",
    "list_project_sources",
    "list_projects",
    "list_recent_research_jobs",
    "list_research_jobs_for_project",
    "list_research_sources",
    "list_snapshots_for_project",
    "list_work_items_for_project",
    "record_catalog_import",
    "transaction",
    "upsert_authorized_user",
    "upsert_catalog_project",
    "upsert_discord_mapping",
    "upsert_evidence",
    "upsert_milestone",
    "upsert_note",
    "upsert_project",
    "upsert_project_source",
    "upsert_repository_snapshot",
    "upsert_research_job",
    "upsert_research_report",
    "upsert_research_source",
    "upsert_work_item",
]
