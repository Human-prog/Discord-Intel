"""Data-access repositories for Phase 4 entities.

Each repository encapsulates SQL for a single entity type, accepting validated
domain objects and returning domain-friendly results.  Callers must not construct
raw SQL strings carrying arbitrary commands.

Public API:
- Each repository accepts a connection from `get_conn()` or the `transaction()`
  helper, so the caller retains transaction control.
- All queries use `?` parameterisation; no string interpolation of user-supplied
  values is permitted.
- Sensitive fields (tokens, keys, secrets) are never stored in these tables;
  only references and hashes are persisted.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


# =========================================================================
# Project
# =========================================================================


class Project:
    __slots__ = ("allowed_root", "created_at_utc", "description", "id", "name", "updated_at_utc")

    def __init__(
        self,
        id: int,
        name: str,
        description: str | None,
        allowed_root: str,
        created_at_utc: str,
        updated_at_utc: str,
    ) -> None:
        self.id = id
        self.name = name
        self.description = description
        self.allowed_root = allowed_root
        self.created_at_utc = created_at_utc
        self.updated_at_utc = updated_at_utc


def upsert_project(
    conn: sqlite3.Connection, name: str, description: str | None, allowed_root: str
) -> Project:
    row = conn.execute(
        """
        INSERT INTO projects (name, description, allowed_root, created_at_utc, updated_at_utc)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(name, allowed_root) DO UPDATE
        SET description = excluded.description,
            updated_at_utc = excluded.updated_at_utc
        RETURNING id, name, description, allowed_root, created_at_utc, updated_at_utc
        """,
        (name, description, allowed_root, _utc_now(), _utc_now()),
    ).fetchone()
    if row is None:
        raise ValueError("Project upsert returned no row")
    return Project(
        id=row[0],
        name=row[1],
        description=row[2],
        allowed_root=row[3],
        created_at_utc=row[4],
        updated_at_utc=row[5],
    )


def get_project_by_root(conn: sqlite3.Connection, allowed_root: str) -> Project | None:
    row = conn.execute(
        "SELECT id, name, description, allowed_root, created_at_utc, updated_at_utc FROM projects WHERE allowed_root = ?",
        (allowed_root,),
    ).fetchone()
    if row is None:
        return None
    return Project(
        id=row[0],
        name=row[1],
        description=row[2],
        allowed_root=row[3],
        created_at_utc=row[4],
        updated_at_utc=row[5],
    )


def get_project_by_id(conn: sqlite3.Connection, project_id: int) -> Project | None:
    row = conn.execute(
        "SELECT id, name, description, allowed_root, created_at_utc, updated_at_utc "
        "FROM projects WHERE id = ?",
        (project_id,),
    ).fetchone()
    if row is None:
        return None
    return Project(
        id=row[0],
        name=row[1],
        description=row[2],
        allowed_root=row[3],
        created_at_utc=row[4],
        updated_at_utc=row[5],
    )


def get_latest_health_snapshot(conn: sqlite3.Connection, project_id: int) -> tuple[str, str] | None:
    """Return ``(status, checked_at_utc)`` for the newest snapshot, or None."""
    row = conn.execute(
        "SELECT status, checked_at_utc FROM health_snapshots "
        "WHERE project_id = ? ORDER BY checked_at_utc DESC, id DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    if row is None:
        return None
    return str(row[0]), str(row[1])


def list_projects(conn: sqlite3.Connection) -> list[Project]:
    rows = conn.execute(
        "SELECT id, name, description, allowed_root, created_at_utc, updated_at_utc FROM projects ORDER BY name"
    ).fetchall()
    return [
        Project(
            id=r[0],
            name=r[1],
            description=r[2],
            allowed_root=r[3],
            created_at_utc=r[4],
            updated_at_utc=r[5],
        )
        for r in rows
    ]


# =========================================================================
# ProjectSource
# =========================================================================


class ProjectSource:
    __slots__ = (
        "evidence_count",
        "id",
        "last_checked_utc",
        "notes",
        "project_id",
        "source_identifier",
        "source_type",
        "status",
        "url",
    )

    def __init__(
        self,
        id: int,
        project_id: int,
        source_type: str,
        source_identifier: str,
        url: str | None,
        last_checked_utc: str,
        status: str,
        evidence_count: int,
        notes: str | None,
    ) -> None:
        self.id = id
        self.project_id = project_id
        self.source_type = source_type
        self.source_identifier = source_identifier
        self.url = url
        self.last_checked_utc = last_checked_utc
        self.status = status
        self.evidence_count = evidence_count
        self.notes = notes


def upsert_project_source(
    conn: sqlite3.Connection,
    project_id: int,
    source_type: str,
    source_identifier: str,
    url: str | None,
) -> ProjectSource:
    row = conn.execute(
        """
        INSERT INTO project_sources (project_id, source_type, source_identifier, url, last_checked_utc, status, evidence_count, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id, source_type, source_identifier) DO UPDATE
        SET url = excluded.url,
            last_checked_utc = excluded.last_checked_utc,
            status = excluded.status,
            evidence_count = excluded.evidence_count,
            notes = excluded.notes
        RETURNING id, project_id, source_type, source_identifier, url, last_checked_utc, status, evidence_count, notes
        """,
        (project_id, source_type, source_identifier, url, _utc_now(), "active", 0, None),
    ).fetchone()
    if row is None:
        raise ValueError("ProjectSource upsert returned no row")
    return ProjectSource(
        id=row[0],
        project_id=row[1],
        source_type=row[2],
        source_identifier=row[3],
        url=row[4],
        last_checked_utc=row[5],
        status=row[6],
        evidence_count=row[7],
        notes=row[8],
    )


def list_project_sources(conn: sqlite3.Connection, project_id: int) -> list[ProjectSource]:
    rows = conn.execute(
        "SELECT id, project_id, source_type, source_identifier, url, last_checked_utc, status, evidence_count, notes "
        "FROM project_sources WHERE project_id = ? ORDER BY source_type",
        (project_id,),
    ).fetchall()
    return [
        ProjectSource(
            id=r[0],
            project_id=r[1],
            source_type=r[2],
            source_identifier=r[3],
            url=r[4],
            last_checked_utc=r[5],
            status=r[6],
            evidence_count=r[7],
            notes=r[8],
        )
        for r in rows
    ]


# =========================================================================
# DiscordMapping
# =========================================================================


class DiscordMapping:
    __slots__ = ("channel_id", "command_name", "created_at_utc", "guild_id", "id", "project_id")

    def __init__(
        self,
        id: int,
        project_id: int,
        guild_id: int,
        channel_id: int,
        command_name: str,
        created_at_utc: str,
    ) -> None:
        self.id = id
        self.project_id = project_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.command_name = command_name
        self.created_at_utc = created_at_utc


def upsert_discord_mapping(
    conn: sqlite3.Connection, project_id: int, guild_id: int, channel_id: int, command_name: str
) -> DiscordMapping:
    row = conn.execute(
        """
        INSERT INTO discord_mappings (project_id, guild_id, channel_id, command_name, created_at_utc)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(project_id, guild_id, channel_id, command_name) DO UPDATE
        SET created_at_utc = excluded.created_at_utc
        RETURNING id, project_id, guild_id, channel_id, command_name, created_at_utc
        """,
        (project_id, guild_id, channel_id, command_name, _utc_now()),
    ).fetchone()
    if row is None:
        raise ValueError("DiscordMapping upsert returned no row")
    return DiscordMapping(
        id=row[0],
        project_id=row[1],
        guild_id=row[2],
        channel_id=row[3],
        command_name=row[4],
        created_at_utc=row[5],
    )


def get_mapping(
    conn: sqlite3.Connection, project_id: int, guild_id: int, channel_id: int, command_name: str
) -> DiscordMapping | None:
    row = conn.execute(
        "SELECT id, project_id, guild_id, channel_id, command_name, created_at_utc FROM discord_mappings "
        "WHERE project_id = ? AND guild_id = ? AND channel_id = ? AND command_name = ?",
        (project_id, guild_id, channel_id, command_name),
    ).fetchone()
    if row is None:
        return None
    return DiscordMapping(
        id=row[0],
        project_id=row[1],
        guild_id=row[2],
        channel_id=row[3],
        command_name=row[4],
        created_at_utc=row[5],
    )


def get_mapped_project_id(
    conn: sqlite3.Connection, guild_id: int, channel_id: int, command_name: str
) -> int | None:
    """Resolve the project mapped to a guild/channel/command, if any."""
    row = conn.execute(
        "SELECT project_id FROM discord_mappings "
        "WHERE guild_id = ? AND channel_id = ? AND command_name = ?",
        (guild_id, channel_id, command_name),
    ).fetchone()
    return int(row[0]) if row is not None else None


def list_mappings_for_project(conn: sqlite3.Connection, project_id: int) -> list[DiscordMapping]:
    rows = conn.execute(
        "SELECT id, project_id, guild_id, channel_id, command_name, created_at_utc FROM discord_mappings "
        "WHERE project_id = ? ORDER BY command_name",
        (project_id,),
    ).fetchall()
    return [
        DiscordMapping(
            id=r[0],
            project_id=r[1],
            guild_id=r[2],
            channel_id=r[3],
            command_name=r[4],
            created_at_utc=r[5],
        )
        for r in rows
    ]


# =========================================================================
# AuthorizedUser
# =========================================================================


class AuthorizedUser:
    __slots__ = ("discord_user_id", "granted_at_utc", "id", "project_id", "role")

    def __init__(
        self, id: int, discord_user_id: int, project_id: int | None, role: str, granted_at_utc: str
    ) -> None:
        self.id = id
        self.discord_user_id = discord_user_id
        self.project_id = project_id
        self.role = role
        self.granted_at_utc = granted_at_utc


def upsert_authorized_user(
    conn: sqlite3.Connection, discord_user_id: int, project_id: int | None, role: str = "member"
) -> AuthorizedUser:
    row = conn.execute(
        """
        INSERT INTO authorized_users (discord_user_id, project_id, role, granted_at_utc)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(discord_user_id, project_id) DO UPDATE
        SET role = excluded.role,
            granted_at_utc = excluded.granted_at_utc
        RETURNING id, discord_user_id, project_id, role, granted_at_utc
        """,
        (discord_user_id, project_id, role, _utc_now()),
    ).fetchone()
    if row is None:
        raise ValueError("AuthorizedUser upsert returned no row")
    return AuthorizedUser(
        id=row[0], discord_user_id=row[1], project_id=row[2], role=row[3], granted_at_utc=row[4]
    )


def get_authorized_user(
    conn: sqlite3.Connection, discord_user_id: int, project_id: int
) -> AuthorizedUser | None:
    row = conn.execute(
        "SELECT id, discord_user_id, project_id, role, granted_at_utc FROM authorized_users "
        "WHERE discord_user_id = ? AND project_id = ?",
        (discord_user_id, project_id),
    ).fetchone()
    if row is None:
        return None
    return AuthorizedUser(
        id=row[0], discord_user_id=row[1], project_id=row[2], role=row[3], granted_at_utc=row[4]
    )


def list_authorized_users_for_project(
    conn: sqlite3.Connection, project_id: int
) -> list[AuthorizedUser]:
    rows = conn.execute(
        "SELECT id, discord_user_id, project_id, role, granted_at_utc FROM authorized_users "
        "WHERE project_id = ? ORDER BY discord_user_id",
        (project_id,),
    ).fetchall()
    return [
        AuthorizedUser(
            id=r[0], discord_user_id=r[1], project_id=r[2], role=r[3], granted_at_utc=r[4]
        )
        for r in rows
    ]


# =========================================================================
# Note
# =========================================================================


class Note:
    __slots__ = (
        "content",
        "created_at_utc",
        "discord_user_id",
        "id",
        "project_id",
        "updated_at_utc",
    )

    def __init__(
        self,
        id: int,
        project_id: int,
        discord_user_id: int | None,
        content: str,
        created_at_utc: str,
        updated_at_utc: str,
    ) -> None:
        self.id = id
        self.project_id = project_id
        self.discord_user_id = discord_user_id
        self.content = content
        self.created_at_utc = created_at_utc
        self.updated_at_utc = updated_at_utc


def upsert_note(
    conn: sqlite3.Connection, project_id: int, discord_user_id: int | None, content: str
) -> Note:
    row = conn.execute(
        """
        INSERT INTO notes (project_id, discord_user_id, content, created_at_utc, updated_at_utc)
        VALUES (?, ?, ?, ?, ?)
        RETURNING id, project_id, discord_user_id, content, created_at_utc, updated_at_utc
        """,
        (project_id, discord_user_id, content, _utc_now(), _utc_now()),
    ).fetchone()
    if row is None:
        raise ValueError("Note upsert returned no row")
    return Note(
        id=row[0],
        project_id=row[1],
        discord_user_id=row[2],
        content=row[3],
        created_at_utc=row[4],
        updated_at_utc=row[5],
    )


def list_notes_for_project(conn: sqlite3.Connection, project_id: int) -> list[Note]:
    rows = conn.execute(
        "SELECT id, project_id, discord_user_id, content, created_at_utc, updated_at_utc FROM notes "
        "WHERE project_id = ? ORDER BY created_at_utc DESC",
        (project_id,),
    ).fetchall()
    return [
        Note(
            id=r[0],
            project_id=r[1],
            discord_user_id=r[2],
            content=r[3],
            created_at_utc=r[4],
            updated_at_utc=r[5],
        )
        for r in rows
    ]


# =========================================================================
# Milestone
# =========================================================================


class Milestone:
    __slots__ = (
        "completed_at_utc",
        "created_at_utc",
        "description",
        "id",
        "project_id",
        "status",
        "target_date_utc",
        "title",
    )

    def __init__(
        self,
        id: int,
        project_id: int,
        title: str,
        description: str | None,
        status: str,
        target_date_utc: str | None,
        completed_at_utc: str | None,
        created_at_utc: str,
    ) -> None:
        self.id = id
        self.project_id = project_id
        self.title = title
        self.description = description
        self.status = status
        self.target_date_utc = target_date_utc
        self.completed_at_utc = completed_at_utc
        self.created_at_utc = created_at_utc


def upsert_milestone(
    conn: sqlite3.Connection,
    project_id: int,
    title: str,
    description: str | None,
    status: str,
    target_date_utc: str | None,
) -> Milestone:
    row = conn.execute(
        """
        INSERT INTO milestones (project_id, title, description, status, target_date_utc, created_at_utc)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id, title) DO UPDATE
        SET description = excluded.description,
            status = excluded.status,
            target_date_utc = excluded.target_date_utc,
            created_at_utc = excluded.created_at_utc
        RETURNING id, project_id, title, description, status, target_date_utc, completed_at_utc, created_at_utc
        """,
        (project_id, title, description, status, target_date_utc, _utc_now()),
    ).fetchone()
    if row is None:
        raise ValueError("Milestone upsert returned no row")
    return Milestone(
        id=row[0],
        project_id=row[1],
        title=row[2],
        description=row[3],
        status=row[4],
        target_date_utc=row[5],
        completed_at_utc=row[6],
        created_at_utc=row[7],
    )


def list_milestones_for_project(conn: sqlite3.Connection, project_id: int) -> list[Milestone]:
    rows = conn.execute(
        "SELECT id, project_id, title, description, status, target_date_utc, completed_at_utc, created_at_utc "
        "FROM milestones WHERE project_id = ? ORDER BY status, title",
        (project_id,),
    ).fetchall()
    return [
        Milestone(
            id=r[0],
            project_id=r[1],
            title=r[2],
            description=r[3],
            status=r[4],
            target_date_utc=r[5],
            completed_at_utc=r[6],
            created_at_utc=r[7],
        )
        for r in rows
    ]


# =========================================================================
# Evidence
# =========================================================================


class Evidence:
    __slots__ = (
        "claim",
        "confidence",
        "content_hash",
        "id",
        "is_stale",
        "project_id",
        "relevance_score",
        "retrieved_at_utc",
        "source_id",
        "title",
    )

    def __init__(
        self,
        id: int,
        project_id: int,
        source_id: int | None,
        title: str,
        content_hash: str,
        retrieved_at_utc: str,
        confidence: float,
        claim: str | None,
        is_stale: int,
        relevance_score: float,
    ) -> None:
        self.id = id
        self.project_id = project_id
        self.source_id = source_id
        self.title = title
        self.content_hash = content_hash
        self.retrieved_at_utc = retrieved_at_utc
        self.confidence = confidence
        self.claim = claim
        self.is_stale = is_stale
        self.relevance_score = relevance_score


def upsert_evidence(
    conn: sqlite3.Connection,
    project_id: int,
    source_id: int | None,
    title: str,
    content_hash: str,
    confidence: float,
    claim: str | None,
) -> Evidence:
    row = conn.execute(
        """
        INSERT INTO evidence (project_id, source_id, title, content_hash, retrieved_at_utc, confidence, claim, is_stale, relevance_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id, source_id, title) DO UPDATE
        SET title = excluded.title,
            content_hash = excluded.content_hash,
            retrieved_at_utc = excluded.retrieved_at_utc,
            confidence = excluded.confidence,
            claim = excluded.claim,
            is_stale = excluded.is_stale,
            relevance_score = excluded.relevance_score
        RETURNING id, project_id, source_id, title, content_hash, retrieved_at_utc, confidence, claim, is_stale, relevance_score
        """,
        (
            project_id,
            source_id,
            title,
            content_hash,
            _utc_now(),
            confidence,
            claim,
            0 if confidence > 0 else 1,
            0.0,
        ),
    ).fetchone()
    if row is None:
        raise ValueError("Evidence upsert returned no row")
    return Evidence(
        id=row[0],
        project_id=row[1],
        source_id=row[2],
        title=row[3],
        content_hash=row[4],
        retrieved_at_utc=row[5],
        confidence=row[6],
        claim=row[7],
        is_stale=row[8],
        relevance_score=row[9],
    )


def list_evidence_for_project(conn: sqlite3.Connection, project_id: int) -> list[Evidence]:
    rows = conn.execute(
        "SELECT id, project_id, source_id, title, content_hash, retrieved_at_utc, confidence, claim, is_stale, relevance_score "
        "FROM evidence WHERE project_id = ? ORDER BY retrieved_at_utc DESC",
        (project_id,),
    ).fetchall()
    return [
        Evidence(
            id=r[0],
            project_id=r[1],
            source_id=r[2],
            title=r[3],
            content_hash=r[4],
            retrieved_at_utc=r[5],
            confidence=r[6],
            claim=r[7],
            is_stale=r[8],
            relevance_score=r[9],
        )
        for r in rows
    ]


def get_evidence(conn: sqlite3.Connection, project_id: int, evidence_id: int) -> Evidence | None:
    """Fetch one evidence record scoped to a project, or None."""
    row = conn.execute(
        "SELECT id, project_id, source_id, title, content_hash, retrieved_at_utc, confidence, claim, is_stale, relevance_score "
        "FROM evidence WHERE id = ? AND project_id = ?",
        (evidence_id, project_id),
    ).fetchone()
    if row is None:
        return None
    return Evidence(
        id=row[0],
        project_id=row[1],
        source_id=row[2],
        title=row[3],
        content_hash=row[4],
        retrieved_at_utc=row[5],
        confidence=row[6],
        claim=row[7],
        is_stale=row[8],
        relevance_score=row[9],
    )


# =========================================================================
# RepositorySnapshot
# =========================================================================


class RepositorySnapshot:
    __slots__ = (
        "file_state_hash",
        "git_branch",
        "git_commit_hash",
        "id",
        "notes",
        "project_id",
        "snapshot_time_utc",
        "status",
    )

    def __init__(
        self,
        id: int,
        project_id: int,
        git_commit_hash: str,
        git_branch: str,
        snapshot_time_utc: str,
        file_state_hash: str | None,
        status: str,
        notes: str | None,
    ) -> None:
        self.id = id
        self.project_id = project_id
        self.git_commit_hash = git_commit_hash
        self.git_branch = git_branch
        self.snapshot_time_utc = snapshot_time_utc
        self.file_state_hash = file_state_hash
        self.status = status
        self.notes = notes


def upsert_repository_snapshot(
    conn: sqlite3.Connection,
    project_id: int,
    git_commit_hash: str,
    git_branch: str,
    file_state_hash: str | None,
) -> RepositorySnapshot:
    row = conn.execute(
        """
        INSERT INTO repository_snapshots (project_id, git_commit_hash, git_branch, snapshot_time_utc, file_state_hash, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id, git_commit_hash) DO UPDATE
        SET git_branch = excluded.git_branch,
            snapshot_time_utc = excluded.snapshot_time_utc,
            file_state_hash = excluded.file_state_hash,
            status = excluded.status,
            notes = excluded.notes
        RETURNING id, project_id, git_commit_hash, git_branch, snapshot_time_utc, file_state_hash, status, notes
        """,
        (project_id, git_commit_hash, git_branch, _utc_now(), file_state_hash, "verified", None),
    ).fetchone()
    if row is None:
        raise ValueError("RepositorySnapshot upsert returned no row")
    return RepositorySnapshot(
        id=row[0],
        project_id=row[1],
        git_commit_hash=row[2],
        git_branch=row[3],
        snapshot_time_utc=row[4],
        file_state_hash=row[5],
        status=row[6],
        notes=row[7],
    )


def list_snapshots_for_project(
    conn: sqlite3.Connection, project_id: int
) -> list[RepositorySnapshot]:
    rows = conn.execute(
        "SELECT id, project_id, git_commit_hash, git_branch, snapshot_time_utc, file_state_hash, status, notes "
        "FROM repository_snapshots WHERE project_id = ? ORDER BY snapshot_time_utc DESC",
        (project_id,),
    ).fetchall()
    return [
        RepositorySnapshot(
            id=r[0],
            project_id=r[1],
            git_commit_hash=r[2],
            git_branch=r[3],
            snapshot_time_utc=r[4],
            file_state_hash=r[5],
            status=r[6],
            notes=r[7],
        )
        for r in rows
    ]


# =========================================================================
# ResearchJob
# =========================================================================


class ResearchJob:
    __slots__ = (
        "completed_at_utc",
        "id",
        "model_used",
        "project_id",
        "question",
        "result_summary",
        "started_at_utc",
        "status",
        "user_id",
    )

    def __init__(
        self,
        id: int,
        project_id: int,
        user_id: int | None,
        question: str,
        status: str,
        started_at_utc: str,
        completed_at_utc: str | None,
        result_summary: str | None,
        model_used: str | None,
    ) -> None:
        self.id = id
        self.project_id = project_id
        self.user_id = user_id
        self.question = question
        self.status = status
        self.started_at_utc = started_at_utc
        self.completed_at_utc = completed_at_utc
        self.result_summary = result_summary
        self.model_used = model_used


def upsert_research_job(
    conn: sqlite3.Connection,
    project_id: int,
    user_id: int | None,
    question: str,
    status: str = "pending",
    model_used: str | None = None,
) -> ResearchJob:
    row = conn.execute(
        """
        INSERT INTO research_jobs (project_id, user_id, question, status, started_at_utc, completed_at_utc, result_summary, model_used)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id, question) DO UPDATE
        SET status = excluded.status,
            started_at_utc = excluded.started_at_utc,
            completed_at_utc = excluded.completed_at_utc,
            result_summary = excluded.result_summary,
            model_used = excluded.model_used
        RETURNING id, project_id, user_id, question, status, started_at_utc, completed_at_utc, result_summary, model_used
        """,
        (project_id, user_id, question, status, _utc_now(), None, None, model_used),
    ).fetchone()
    if row is None:
        raise ValueError("ResearchJob upsert returned no row")
    return ResearchJob(
        id=row[0],
        project_id=row[1],
        user_id=row[2],
        question=row[3],
        status=row[4],
        started_at_utc=row[5],
        completed_at_utc=row[6],
        result_summary=row[7],
        model_used=row[8],
    )


def list_research_jobs_for_project(conn: sqlite3.Connection, project_id: int) -> list[ResearchJob]:
    rows = conn.execute(
        "SELECT id, project_id, user_id, question, status, started_at_utc, completed_at_utc, result_summary, model_used "
        "FROM research_jobs WHERE project_id = ? ORDER BY started_at_utc DESC",
        (project_id,),
    ).fetchall()
    return [
        ResearchJob(
            id=r[0],
            project_id=r[1],
            user_id=r[2],
            question=r[3],
            status=r[4],
            started_at_utc=r[5],
            completed_at_utc=r[6],
            result_summary=r[7],
            model_used=r[8],
        )
        for r in rows
    ]


# =========================================================================
# ResearchSource
# =========================================================================


class ResearchSource:
    __slots__ = (
        "canonical_url",
        "content_hash",
        "id",
        "research_job_id",
        "retrieved_at_utc",
        "source_type",
        "title",
    )

    def __init__(
        self,
        id: int,
        research_job_id: int,
        title: str,
        canonical_url: str | None,
        source_type: str,
        retrieved_at_utc: str,
        content_hash: str,
    ) -> None:
        self.id = id
        self.research_job_id = research_job_id
        self.title = title
        self.canonical_url = canonical_url
        self.source_type = source_type
        self.retrieved_at_utc = retrieved_at_utc
        self.content_hash = content_hash


def upsert_research_source(
    conn: sqlite3.Connection,
    research_job_id: int,
    title: str,
    canonical_url: str | None,
    source_type: str,
    content_hash: str,
) -> ResearchSource:
    row = conn.execute(
        """
        INSERT INTO research_sources (research_job_id, title, canonical_url, source_type, retrieved_at_utc, content_hash)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(research_job_id, title) DO UPDATE
        SET canonical_url = excluded.canonical_url,
            source_type = excluded.source_type,
            retrieved_at_utc = excluded.retrieved_at_utc,
            content_hash = excluded.content_hash
        RETURNING id, research_job_id, title, canonical_url, source_type, retrieved_at_utc, content_hash
        """,
        (research_job_id, title, canonical_url, source_type, _utc_now(), content_hash),
    ).fetchone()
    if row is None:
        raise ValueError("ResearchSource upsert returned no row")
    return ResearchSource(
        id=row[0],
        research_job_id=row[1],
        title=row[2],
        canonical_url=row[3],
        source_type=row[4],
        retrieved_at_utc=row[5],
        content_hash=row[6],
    )
