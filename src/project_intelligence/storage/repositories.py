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


_PROJECT_COLUMNS = (
    "id, name, description, allowed_root, created_at_utc, updated_at_utc, "
    "catalog_key, catalog_status, category, priority, tech_stack_json, repo_url, "
    "local_path, last_activity_utc, source, monitored, metadata_json"
)


class Project:
    __slots__ = (
        "allowed_root",
        "catalog_key",
        "catalog_status",
        "category",
        "created_at_utc",
        "description",
        "id",
        "last_activity_utc",
        "local_path",
        "metadata_json",
        "monitored",
        "name",
        "priority",
        "repo_url",
        "source",
        "tech_stack_json",
        "updated_at_utc",
    )

    def __init__(
        self,
        id: int,
        name: str,
        description: str | None,
        allowed_root: str,
        created_at_utc: str,
        updated_at_utc: str,
        *,
        catalog_key: str | None = None,
        catalog_status: str = "unknown",
        category: str | None = None,
        priority: str | None = None,
        tech_stack_json: str | None = None,
        repo_url: str | None = None,
        local_path: str | None = None,
        last_activity_utc: str | None = None,
        source: str = "manual",
        monitored: int = 1,
        metadata_json: str | None = None,
    ) -> None:
        self.id = id
        self.name = name
        self.description = description
        self.allowed_root = allowed_root
        self.created_at_utc = created_at_utc
        self.updated_at_utc = updated_at_utc
        self.catalog_key = catalog_key
        self.catalog_status = catalog_status
        self.category = category
        self.priority = priority
        self.tech_stack_json = tech_stack_json
        self.repo_url = repo_url
        self.local_path = local_path
        self.last_activity_utc = last_activity_utc
        self.source = source
        self.monitored = monitored
        self.metadata_json = metadata_json


def _project_from_row(row: sqlite3.Row | tuple[object, ...]) -> Project:
    return Project(
        id=int(row[0]),  # type: ignore[arg-type]
        name=str(row[1]),
        description=row[2] if row[2] is None else str(row[2]),
        allowed_root=str(row[3]),
        created_at_utc=str(row[4]),
        updated_at_utc=str(row[5]),
        catalog_key=row[6] if row[6] is None else str(row[6]),
        catalog_status=str(row[7]),
        category=row[8] if row[8] is None else str(row[8]),
        priority=row[9] if row[9] is None else str(row[9]),
        tech_stack_json=row[10] if row[10] is None else str(row[10]),
        repo_url=row[11] if row[11] is None else str(row[11]),
        local_path=row[12] if row[12] is None else str(row[12]),
        last_activity_utc=row[13] if row[13] is None else str(row[13]),
        source=str(row[14]),
        monitored=int(row[15]),  # type: ignore[arg-type]
        metadata_json=row[16] if row[16] is None else str(row[16]),
    )


def upsert_project(
    conn: sqlite3.Connection, name: str, description: str | None, allowed_root: str
) -> Project:
    row = conn.execute(
        f"""
        INSERT INTO projects (name, description, allowed_root, created_at_utc, updated_at_utc)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(name, allowed_root) DO UPDATE
        SET description = excluded.description,
            updated_at_utc = excluded.updated_at_utc
        RETURNING {_PROJECT_COLUMNS}
        """,
        (name, description, allowed_root, _utc_now(), _utc_now()),
    ).fetchone()
    if row is None:
        raise ValueError("Project upsert returned no row")
    return _project_from_row(row)


def _update_catalog_project(
    conn: sqlite3.Connection,
    project_id: int,
    *,
    catalog_key: str,
    name: str,
    description: str | None,
    local_path: str,
    repo_url: str | None,
    tech_stack_json: str | None,
    category: str | None,
    priority: str | None,
    catalog_status: str,
    last_activity_utc: str | None,
    metadata_json: str | None,
    source: str,
    monitored: int,
) -> Project:
    row = conn.execute(
        f"""
        UPDATE projects
        SET name = ?, description = ?, allowed_root = ?, updated_at_utc = ?,
            catalog_key = ?, catalog_status = ?, category = ?, priority = ?,
            tech_stack_json = ?, repo_url = ?, local_path = ?, last_activity_utc = ?,
            source = ?, monitored = ?, metadata_json = ?
        WHERE id = ?
        RETURNING {_PROJECT_COLUMNS}
        """,
        (
            name,
            description,
            local_path,
            _utc_now(),
            catalog_key,
            catalog_status,
            category,
            priority,
            tech_stack_json,
            repo_url,
            local_path,
            last_activity_utc,
            source,
            monitored,
            metadata_json,
            project_id,
        ),
    ).fetchone()
    if row is None:
        raise ValueError("Project update returned no row")
    return _project_from_row(row)


def upsert_catalog_project(
    conn: sqlite3.Connection,
    *,
    catalog_key: str,
    name: str,
    description: str | None,
    local_path: str,
    repo_url: str | None = None,
    tech_stack_json: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    catalog_status: str = "unknown",
    last_activity_utc: str | None = None,
    metadata_json: str | None = None,
    source: str = "catalog",
    monitored: int = 0,
) -> Project:
    """Insert or update a project discovered by the workstation catalog scan.

    The lookup prefers the stable ``catalog_key`` (a hash of the resolved
    source path) and falls back to the source path so a re-scan after a rename
    updates the existing row instead of creating a duplicate.
    """
    row = conn.execute(
        "SELECT id FROM projects WHERE catalog_key = ? OR allowed_root = ? LIMIT 1",
        (catalog_key, local_path),
    ).fetchone()
    if row is not None:
        return _update_catalog_project(
            conn,
            int(row[0]),
            catalog_key=catalog_key,
            name=name,
            description=description,
            local_path=local_path,
            repo_url=repo_url,
            tech_stack_json=tech_stack_json,
            category=category,
            priority=priority,
            catalog_status=catalog_status,
            last_activity_utc=last_activity_utc,
            metadata_json=metadata_json,
            source=source,
            monitored=monitored,
        )

    row = conn.execute(
        f"""
        INSERT INTO projects (
            name, description, allowed_root, created_at_utc, updated_at_utc,
            catalog_key, catalog_status, category, priority, tech_stack_json,
            repo_url, local_path, last_activity_utc, source, monitored, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING {_PROJECT_COLUMNS}
        """,
        (
            name,
            description,
            local_path,
            _utc_now(),
            _utc_now(),
            catalog_key,
            catalog_status,
            category,
            priority,
            tech_stack_json,
            repo_url,
            local_path,
            last_activity_utc,
            source,
            monitored,
            metadata_json,
        ),
    ).fetchone()
    if row is None:
        raise ValueError("Catalog project upsert returned no row")
    return _project_from_row(row)


def get_project_by_root(conn: sqlite3.Connection, allowed_root: str) -> Project | None:
    row = conn.execute(
        f"SELECT {_PROJECT_COLUMNS} FROM projects WHERE allowed_root = ?",
        (allowed_root,),
    ).fetchone()
    if row is None:
        return None
    return _project_from_row(row)


def get_project_by_catalog_key(conn: sqlite3.Connection, catalog_key: str) -> Project | None:
    row = conn.execute(
        f"SELECT {_PROJECT_COLUMNS} FROM projects WHERE catalog_key = ?",
        (catalog_key,),
    ).fetchone()
    if row is None:
        return None
    return _project_from_row(row)


def get_project_by_id(conn: sqlite3.Connection, project_id: int) -> Project | None:
    row = conn.execute(
        f"SELECT {_PROJECT_COLUMNS} FROM projects WHERE id = ?",
        (project_id,),
    ).fetchone()
    if row is None:
        return None
    return _project_from_row(row)


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
    rows = conn.execute(f"SELECT {_PROJECT_COLUMNS} FROM projects ORDER BY name").fetchall()
    return [_project_from_row(r) for r in rows]


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


def get_any_mapped_project_id(
    conn: sqlite3.Connection, guild_id: int, channel_id: int
) -> int | None:
    """Resolve any project mapped to this guild/channel.

    Used by commands such as ``/research`` that may not have their own mapping
    yet but should still operate in the context of the channel's project.
    """
    row = conn.execute(
        "SELECT project_id FROM discord_mappings "
        "WHERE guild_id = ? AND channel_id = ? ORDER BY id LIMIT 1",
        (guild_id, channel_id),
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
# WorkItem
# =========================================================================


class WorkItem:
    __slots__ = (
        "body",
        "created_at_utc",
        "external_id",
        "id",
        "metadata_json",
        "occurred_at_utc",
        "project_id",
        "source",
        "status",
        "title",
        "work_type",
    )

    def __init__(
        self,
        id: int,
        project_id: int,
        work_type: str,
        title: str,
        body: str | None,
        status: str,
        source: str,
        external_id: str | None,
        occurred_at_utc: str | None,
        created_at_utc: str,
        metadata_json: str | None,
    ) -> None:
        self.id = id
        self.project_id = project_id
        self.work_type = work_type
        self.title = title
        self.body = body
        self.status = status
        self.source = source
        self.external_id = external_id
        self.occurred_at_utc = occurred_at_utc
        self.created_at_utc = created_at_utc
        self.metadata_json = metadata_json


_WORK_ITEM_COLUMNS = (
    "id, project_id, work_type, title, body, status, source, external_id, "
    "occurred_at_utc, created_at_utc, metadata_json"
)


def _work_item_from_row(row: sqlite3.Row | tuple[object, ...]) -> WorkItem:
    return WorkItem(
        id=int(row[0]),  # type: ignore[arg-type]
        project_id=int(row[1]),  # type: ignore[arg-type]
        work_type=str(row[2]),
        title=str(row[3]),
        body=row[4] if row[4] is None else str(row[4]),
        status=str(row[5]),
        source=str(row[6]),
        external_id=row[7] if row[7] is None else str(row[7]),
        occurred_at_utc=row[8] if row[8] is None else str(row[8]),
        created_at_utc=str(row[9]),
        metadata_json=row[10] if row[10] is None else str(row[10]),
    )


def upsert_work_item(
    conn: sqlite3.Connection,
    project_id: int,
    work_type: str,
    title: str,
    *,
    body: str | None = None,
    status: str = "done",
    source: str = "manual",
    external_id: str | None = None,
    occurred_at_utc: str | None = None,
    metadata_json: str | None = None,
) -> WorkItem:
    """Insert or update one unit of work attached to a project.

    Git commits use ``source='git'`` and the commit hash as ``external_id`` so
    repeated catalog imports stay idempotent.
    """
    row = conn.execute(
        f"""
        INSERT INTO work_items (
            project_id, work_type, title, body, status, source, external_id,
            occurred_at_utc, created_at_utc, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id, source, external_id) DO UPDATE
        SET work_type = excluded.work_type,
            title = excluded.title,
            body = excluded.body,
            status = excluded.status,
            occurred_at_utc = excluded.occurred_at_utc,
            metadata_json = excluded.metadata_json
        RETURNING {_WORK_ITEM_COLUMNS}
        """,
        (
            project_id,
            work_type,
            title,
            body,
            status,
            source,
            external_id,
            occurred_at_utc,
            _utc_now(),
            metadata_json,
        ),
    ).fetchone()
    if row is None:
        raise ValueError("WorkItem upsert returned no row")
    return _work_item_from_row(row)


def list_work_items_for_project(
    conn: sqlite3.Connection, project_id: int, *, limit: int = 100
) -> list[WorkItem]:
    rows = conn.execute(
        f"SELECT {_WORK_ITEM_COLUMNS} FROM work_items WHERE project_id = ? "
        "ORDER BY COALESCE(occurred_at_utc, created_at_utc) DESC, id DESC LIMIT ?",
        (project_id, max(1, min(limit, 500))),
    ).fetchall()
    return [_work_item_from_row(r) for r in rows]


def count_work_items(conn: sqlite3.Connection, project_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM work_items WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    return int(row[0]) if row is not None else 0


# =========================================================================
# CatalogImport
# =========================================================================


class CatalogImport:
    __slots__ = (
        "id",
        "imported_at_utc",
        "metadata_json",
        "project_count",
        "source_checksum",
        "source_name",
        "work_item_count",
    )

    def __init__(
        self,
        id: int,
        source_name: str,
        source_checksum: str,
        imported_at_utc: str,
        project_count: int,
        work_item_count: int,
        metadata_json: str | None,
    ) -> None:
        self.id = id
        self.source_name = source_name
        self.source_checksum = source_checksum
        self.imported_at_utc = imported_at_utc
        self.project_count = project_count
        self.work_item_count = work_item_count
        self.metadata_json = metadata_json


def record_catalog_import(
    conn: sqlite3.Connection,
    *,
    source_name: str,
    source_checksum: str,
    project_count: int,
    work_item_count: int,
    metadata_json: str | None = None,
) -> CatalogImport:
    row = conn.execute(
        """
        INSERT INTO catalog_imports (
            source_name, source_checksum, imported_at_utc, project_count,
            work_item_count, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_checksum) DO UPDATE
        SET source_name = excluded.source_name,
            imported_at_utc = excluded.imported_at_utc,
            project_count = excluded.project_count,
            work_item_count = excluded.work_item_count,
            metadata_json = excluded.metadata_json
        RETURNING id, source_name, source_checksum, imported_at_utc,
                  project_count, work_item_count, metadata_json
        """,
        (
            source_name,
            source_checksum,
            _utc_now(),
            project_count,
            work_item_count,
            metadata_json,
        ),
    ).fetchone()
    if row is None:
        raise ValueError("CatalogImport upsert returned no row")
    return CatalogImport(
        id=int(row[0]),
        source_name=str(row[1]),
        source_checksum=str(row[2]),
        imported_at_utc=str(row[3]),
        project_count=int(row[4]),
        work_item_count=int(row[5]),
        metadata_json=row[6] if row[6] is None else str(row[6]),
    )


def get_catalog_import(conn: sqlite3.Connection, source_checksum: str) -> CatalogImport | None:
    row = conn.execute(
        "SELECT id, source_name, source_checksum, imported_at_utc, project_count, "
        "work_item_count, metadata_json FROM catalog_imports WHERE source_checksum = ?",
        (source_checksum,),
    ).fetchone()
    if row is None:
        return None
    return CatalogImport(
        id=int(row[0]),
        source_name=str(row[1]),
        source_checksum=str(row[2]),
        imported_at_utc=str(row[3]),
        project_count=int(row[4]),
        work_item_count=int(row[5]),
        metadata_json=row[6] if row[6] is None else str(row[6]),
    )


def get_latest_catalog_import(conn: sqlite3.Connection) -> CatalogImport | None:
    """Return the most recently imported catalog, if any."""
    row = conn.execute(
        "SELECT id, source_name, source_checksum, imported_at_utc, project_count, "
        "work_item_count, metadata_json FROM catalog_imports "
        "ORDER BY imported_at_utc DESC, id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    return CatalogImport(
        id=int(row[0]),
        source_name=str(row[1]),
        source_checksum=str(row[2]),
        imported_at_utc=str(row[3]),
        project_count=int(row[4]),
        work_item_count=int(row[5]),
        metadata_json=row[6] if row[6] is None else str(row[6]),
    )


def count_all_work_items(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM work_items").fetchone()
    return int(row[0]) if row is not None else 0


def count_research_jobs(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM research_jobs").fetchone()
    return int(row[0]) if row is not None else 0


def count_research_sources(conn: sqlite3.Connection, research_job_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM research_sources WHERE research_job_id = ?",
        (research_job_id,),
    ).fetchone()
    return int(row[0]) if row is not None else 0


# =========================================================================
# ResearchJob
# =========================================================================


_RESEARCH_JOB_COLUMNS = (
    "id, project_id, user_id, question, status, started_at_utc, completed_at_utc, "
    "result_summary, model_used, scope, provider, error_text"
)


class ResearchJob:
    __slots__ = (
        "completed_at_utc",
        "error_text",
        "id",
        "model_used",
        "project_id",
        "provider",
        "question",
        "result_summary",
        "scope",
        "started_at_utc",
        "status",
        "user_id",
    )

    def __init__(
        self,
        id: int,
        project_id: int | None,
        user_id: int | None,
        question: str,
        status: str,
        started_at_utc: str,
        completed_at_utc: str | None,
        result_summary: str | None,
        model_used: str | None,
        *,
        scope: str = "web",
        provider: str | None = None,
        error_text: str | None = None,
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
        self.scope = scope
        self.provider = provider
        self.error_text = error_text


def _research_job_from_row(row: sqlite3.Row | tuple[object, ...]) -> ResearchJob:
    return ResearchJob(
        id=int(row[0]),  # type: ignore[arg-type]
        project_id=None if row[1] is None else int(row[1]),  # type: ignore[arg-type]
        user_id=None if row[2] is None else int(row[2]),  # type: ignore[arg-type]
        question=str(row[3]),
        status=str(row[4]),
        started_at_utc=str(row[5]),
        completed_at_utc=row[6] if row[6] is None else str(row[6]),
        result_summary=row[7] if row[7] is None else str(row[7]),
        model_used=row[8] if row[8] is None else str(row[8]),
        scope=str(row[9]),
        provider=row[10] if row[10] is None else str(row[10]),
        error_text=row[11] if row[11] is None else str(row[11]),
    )


def upsert_research_job(
    conn: sqlite3.Connection,
    project_id: int | None,
    user_id: int | None,
    question: str,
    status: str = "pending",
    model_used: str | None = None,
    *,
    scope: str = "web",
    provider: str | None = None,
) -> ResearchJob:
    """Create a new research job.  Repeated questions are separate jobs."""
    row = conn.execute(
        f"""
        INSERT INTO research_jobs (
            project_id, user_id, question, status, started_at_utc,
            completed_at_utc, result_summary, model_used, scope, provider
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING {_RESEARCH_JOB_COLUMNS}
        """,
        (
            project_id,
            user_id,
            question,
            status,
            _utc_now(),
            None,
            None,
            model_used,
            scope,
            provider,
        ),
    ).fetchone()
    if row is None:
        raise ValueError("ResearchJob upsert returned no row")
    return _research_job_from_row(row)


def complete_research_job(
    conn: sqlite3.Connection,
    job_id: int,
    *,
    status: str,
    result_summary: str | None = None,
    model_used: str | None = None,
    error_text: str | None = None,
) -> ResearchJob:
    row = conn.execute(
        f"""
        UPDATE research_jobs
        SET status = ?, completed_at_utc = ?, result_summary = ?, model_used = ?,
            error_text = ?
        WHERE id = ?
        RETURNING {_RESEARCH_JOB_COLUMNS}
        """,
        (status, _utc_now(), result_summary, model_used, error_text, job_id),
    ).fetchone()
    if row is None:
        raise ValueError("ResearchJob update returned no row")
    return _research_job_from_row(row)


def get_research_job(conn: sqlite3.Connection, job_id: int) -> ResearchJob | None:
    row = conn.execute(
        f"SELECT {_RESEARCH_JOB_COLUMNS} FROM research_jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    if row is None:
        return None
    return _research_job_from_row(row)


def list_research_jobs_for_project(conn: sqlite3.Connection, project_id: int) -> list[ResearchJob]:
    rows = conn.execute(
        f"SELECT {_RESEARCH_JOB_COLUMNS} FROM research_jobs "
        "WHERE project_id = ? ORDER BY started_at_utc DESC",
        (project_id,),
    ).fetchall()
    return [_research_job_from_row(r) for r in rows]


def list_recent_research_jobs(conn: sqlite3.Connection, *, limit: int = 20) -> list[ResearchJob]:
    rows = conn.execute(
        f"SELECT {_RESEARCH_JOB_COLUMNS} FROM research_jobs "
        "ORDER BY started_at_utc DESC, id DESC LIMIT ?",
        (max(1, min(limit, 100)),),
    ).fetchall()
    return [_research_job_from_row(r) for r in rows]


# =========================================================================
# ResearchSource
# =========================================================================


class ResearchSource:
    __slots__ = (
        "canonical_url",
        "content_hash",
        "id",
        "relevance_score",
        "research_job_id",
        "retrieved_at_utc",
        "snippet",
        "source_ref",
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
        *,
        snippet: str | None = None,
        relevance_score: float = 0.0,
        source_ref: str | None = None,
    ) -> None:
        self.id = id
        self.research_job_id = research_job_id
        self.title = title
        self.canonical_url = canonical_url
        self.source_type = source_type
        self.retrieved_at_utc = retrieved_at_utc
        self.content_hash = content_hash
        self.snippet = snippet
        self.relevance_score = relevance_score
        self.source_ref = source_ref


_RESEARCH_SOURCE_COLUMNS = (
    "id, research_job_id, title, canonical_url, source_type, retrieved_at_utc, "
    "content_hash, snippet, relevance_score, source_ref"
)


def _research_source_from_row(row: sqlite3.Row | tuple[object, ...]) -> ResearchSource:
    return ResearchSource(
        id=int(row[0]),  # type: ignore[arg-type]
        research_job_id=int(row[1]),  # type: ignore[arg-type]
        title=str(row[2]),
        canonical_url=row[3] if row[3] is None else str(row[3]),
        source_type=str(row[4]),
        retrieved_at_utc=str(row[5]),
        content_hash=str(row[6]),
        snippet=row[7] if row[7] is None else str(row[7]),
        relevance_score=float(row[8]),  # type: ignore[arg-type]
        source_ref=row[9] if row[9] is None else str(row[9]),
    )


def upsert_research_source(
    conn: sqlite3.Connection,
    research_job_id: int,
    title: str,
    canonical_url: str | None,
    source_type: str,
    content_hash: str,
    *,
    snippet: str | None = None,
    relevance_score: float = 0.0,
    source_ref: str | None = None,
) -> ResearchSource:
    row = conn.execute(
        f"""
        INSERT INTO research_sources (
            research_job_id, title, canonical_url, source_type, retrieved_at_utc,
            content_hash, snippet, relevance_score, source_ref
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(research_job_id, title) DO UPDATE
        SET canonical_url = excluded.canonical_url,
            source_type = excluded.source_type,
            retrieved_at_utc = excluded.retrieved_at_utc,
            content_hash = excluded.content_hash,
            snippet = excluded.snippet,
            relevance_score = excluded.relevance_score,
            source_ref = excluded.source_ref
        RETURNING {_RESEARCH_SOURCE_COLUMNS}
        """,
        (
            research_job_id,
            title,
            canonical_url,
            source_type,
            _utc_now(),
            content_hash,
            snippet,
            relevance_score,
            source_ref,
        ),
    ).fetchone()
    if row is None:
        raise ValueError("ResearchSource upsert returned no row")
    return _research_source_from_row(row)


def list_research_sources(conn: sqlite3.Connection, research_job_id: int) -> list[ResearchSource]:
    rows = conn.execute(
        f"SELECT {_RESEARCH_SOURCE_COLUMNS} FROM research_sources "
        "WHERE research_job_id = ? ORDER BY relevance_score DESC, id ASC",
        (research_job_id,),
    ).fetchall()
    return [_research_source_from_row(r) for r in rows]


# =========================================================================
# ResearchReport
# =========================================================================


class ResearchReport:
    __slots__ = (
        "citation_count",
        "generated_at_utc",
        "id",
        "model_used",
        "report_text",
        "research_job_id",
    )

    def __init__(
        self,
        id: int,
        research_job_id: int,
        generated_at_utc: str,
        model_used: str | None,
        report_text: str,
        citation_count: int,
    ) -> None:
        self.id = id
        self.research_job_id = research_job_id
        self.generated_at_utc = generated_at_utc
        self.model_used = model_used
        self.report_text = report_text
        self.citation_count = citation_count


def upsert_research_report(
    conn: sqlite3.Connection,
    research_job_id: int,
    report_text: str,
    *,
    model_used: str | None = None,
    citation_count: int = 0,
) -> ResearchReport:
    row = conn.execute(
        """
        INSERT INTO research_reports (
            research_job_id, generated_at_utc, model_used, report_text, citation_count
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(research_job_id) DO UPDATE
        SET generated_at_utc = excluded.generated_at_utc,
            model_used = excluded.model_used,
            report_text = excluded.report_text,
            citation_count = excluded.citation_count
        RETURNING id, research_job_id, generated_at_utc, model_used, report_text, citation_count
        """,
        (research_job_id, _utc_now(), model_used, report_text, citation_count),
    ).fetchone()
    if row is None:
        raise ValueError("ResearchReport upsert returned no row")
    return ResearchReport(
        id=int(row[0]),
        research_job_id=int(row[1]),
        generated_at_utc=str(row[2]),
        model_used=row[3] if row[3] is None else str(row[3]),
        report_text=str(row[4]),
        citation_count=int(row[5]),
    )


def get_research_report(conn: sqlite3.Connection, research_job_id: int) -> ResearchReport | None:
    row = conn.execute(
        "SELECT id, research_job_id, generated_at_utc, model_used, report_text, citation_count "
        "FROM research_reports WHERE research_job_id = ?",
        (research_job_id,),
    ).fetchone()
    if row is None:
        return None
    return ResearchReport(
        id=int(row[0]),
        research_job_id=int(row[1]),
        generated_at_utc=str(row[2]),
        model_used=row[3] if row[3] is None else str(row[3]),
        report_text=str(row[4]),
        citation_count=int(row[5]),
    )
