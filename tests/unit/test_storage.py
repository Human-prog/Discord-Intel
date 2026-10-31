"""Storage layer tests (Phase 4): migrations, repositories, transactions."""

from __future__ import annotations

import pytest

from project_intelligence.health.health_engine import store_health_snapshot
from project_intelligence.storage import repositories as repo
from project_intelligence.storage.database import transaction


def _project(db, name: str = "Alpha", root: str = "/srv/alpha"):
    return repo.upsert_project(db, name, "A test project", root)


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------


def test_migrations_create_expected_tables(db) -> None:
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "projects",
        "project_sources",
        "discord_mappings",
        "authorized_users",
        "notes",
        "milestones",
        "evidence",
        "repository_snapshots",
        "research_jobs",
        "research_sources",
        "research_reports",
        "scheduled_jobs",
        "health_snapshots",
        "agent_tasks",
        "audit_events",
        "schema_migrations",
    } <= tables


def test_migration_is_recorded_once(db) -> None:
    rows = db.execute("SELECT migration_name FROM schema_migrations").fetchall()
    names = [row[0] for row in rows]
    assert names.count("001_initial") == 1


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def test_project_roundtrip_and_missing_lookups(db) -> None:
    project = _project(db)
    assert project.id > 0

    by_id = repo.get_project_by_id(db, project.id)
    assert by_id is not None
    assert by_id.name == "Alpha"
    assert by_id.allowed_root == "/srv/alpha"
    assert by_id.created_at_utc.endswith("Z")

    by_root = repo.get_project_by_root(db, "/srv/alpha")
    assert by_root is not None
    assert by_root.id == project.id

    assert repo.get_project_by_id(db, 424242) is None
    assert repo.get_project_by_root(db, "/srv/missing") is None


def test_project_upsert_updates_in_place(db) -> None:
    first = _project(db)
    second = repo.upsert_project(db, "Alpha", "Updated description", "/srv/alpha")
    assert second.id == first.id
    assert second.description == "Updated description"
    assert len(repo.list_projects(db)) == 1


# ---------------------------------------------------------------------------
# Sources, mappings, users, notes
# ---------------------------------------------------------------------------


def test_project_sources_roundtrip(db) -> None:
    project = _project(db)
    source = repo.upsert_project_source(db, project.id, "github", "owner/repo", "https://github.com/owner/repo")
    assert source.project_id == project.id
    assert source.source_type == "github"

    sources = repo.list_project_sources(db, project.id)
    assert [s.source_identifier for s in sources] == ["owner/repo"]


def test_discord_mapping_roundtrip(db) -> None:
    project = _project(db)
    mapping = repo.upsert_discord_mapping(db, project.id, 111, 222, "next")
    assert mapping.command_name == "next"

    found = repo.get_mapping(db, project.id, 111, 222, "next")
    assert found is not None and found.id == mapping.id
    assert repo.get_mapping(db, project.id, 111, 222, "roadmap") is None
    assert len(repo.list_mappings_for_project(db, project.id)) == 1


def test_authorized_users_roundtrip(db) -> None:
    project = _project(db)
    repo.upsert_authorized_user(db, 123, project.id, role="owner")

    user = repo.get_authorized_user(db, 123, project.id)
    assert user is not None
    assert user.role == "owner"
    assert repo.get_authorized_user(db, 123, 999) is None
    assert len(repo.list_authorized_users_for_project(db, project.id)) == 1


def test_notes_roundtrip(db) -> None:
    project = _project(db)
    note = repo.upsert_note(db, project.id, 123, "hello world")
    assert note.content == "hello world"
    notes = repo.list_notes_for_project(db, project.id)
    assert len(notes) == 1
    assert notes[0].id == note.id


# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------


def test_milestone_upsert_is_idempotent(db) -> None:
    project = _project(db)
    first = repo.upsert_milestone(db, project.id, "Ship", "first", "open", None)
    second = repo.upsert_milestone(db, project.id, "Ship", "second", "in_progress", "2026-01-01T00:00:00Z")
    assert second.id == first.id
    assert second.description == "second"
    assert second.status == "in_progress"
    assert second.target_date_utc == "2026-01-01T00:00:00Z"
    assert len(repo.list_milestones_for_project(db, project.id)) == 1


def test_milestone_returns_all_fields(db) -> None:
    project = _project(db)
    milestone = repo.upsert_milestone(db, project.id, "Document", None, "open", None)
    assert milestone.project_id == project.id
    assert milestone.completed_at_utc is None
    assert milestone.created_at_utc.endswith("Z")


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


def test_evidence_roundtrip(db) -> None:
    project = _project(db)
    evidence = repo.upsert_evidence(db, project.id, None, "Proof", "a" * 64, 0.9, "claim text")
    assert evidence.id > 0
    assert evidence.confidence == 0.9
    assert evidence.claim == "claim text"

    fetched = repo.get_evidence(db, project.id, evidence.id)
    assert fetched is not None and fetched.title == "Proof"
    assert repo.get_evidence(db, project.id, 999) is None
    assert repo.get_evidence(db, 999, evidence.id) is None
    assert len(repo.list_evidence_for_project(db, project.id)) == 1


def test_evidence_low_confidence_is_marked_stale(db) -> None:
    project = _project(db)
    evidence = repo.upsert_evidence(db, project.id, None, "Weak", "b" * 64, 0.0, None)
    assert evidence.is_stale == 1


# ---------------------------------------------------------------------------
# Snapshots, research, health
# ---------------------------------------------------------------------------


def test_repository_snapshot_roundtrip(db) -> None:
    project = _project(db)
    snapshot = repo.upsert_repository_snapshot(db, project.id, "deadbeef", "main", "hash")
    assert snapshot.git_commit_hash == "deadbeef"
    assert [s.id for s in repo.list_snapshots_for_project(db, project.id)] == [snapshot.id]


def test_research_job_and_sources_roundtrip(db) -> None:
    project = _project(db)
    job = repo.upsert_research_job(db, project.id, 123, "What next?")
    assert job.status == "pending"
    assert job.question == "What next?"

    source = repo.upsert_research_source(db, job.id, "Docs", "https://docs.example", "web", "c" * 64)
    assert source.research_job_id == job.id
    assert source.content_hash == "c" * 64

    jobs = repo.list_research_jobs_for_project(db, project.id)
    assert len(jobs) == 1


def test_health_snapshots_latest_wins(db) -> None:
    project = _project(db)
    assert repo.get_latest_health_snapshot(db, project.id) is None

    store_health_snapshot(project.id, "healthy", details={"root_exists": True})
    store_health_snapshot(project.id, "unhealthy", details={"root_exists": False})

    latest = repo.get_latest_health_snapshot(db, project.id)
    assert latest is not None
    status, checked_at = latest
    assert status == "unhealthy"
    assert checked_at.endswith("Z")


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------


def test_transaction_commits(db) -> None:
    project = _project(db)

    def work(conn):
        return repo.upsert_note(conn, project.id, None, "inside transaction")

    note = transaction(work)
    assert note.content == "inside transaction"
    assert len(repo.list_notes_for_project(db, project.id)) == 1


def test_transaction_rolls_back_on_error(db) -> None:
    project = _project(db)

    def work(conn):
        repo.upsert_note(conn, project.id, None, "will roll back")
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        transaction(work)

    assert repo.list_notes_for_project(db, project.id) == []
