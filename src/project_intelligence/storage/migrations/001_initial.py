"""Initial migration: create all required Phase 4 entities.

This migration creates the following tables:
- projects
- project_sources
- discord_mappings
- authorized_users
- notes
- milestones
- evidence
- repository_snapshots
- research_jobs
- research_sources
- research_reports
- scheduled_jobs
- health_snapshots
- agent_tasks
- audit_events
- schema_migrations (created by the migration framework)
"""

from typing import Any

MigrationFunc = Any


def up(conn: Any) -> None:
    """Run all table creations in a single transaction for atomicity."""
    conn.execute("BEGIN")

    # ---- schema_migrations is handled by the framework; ensure it exists ----
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            migration_name TEXT NOT NULL UNIQUE,
            applied_at_utc TEXT NOT NULL
        )
        """
    )

    # ---- projects --------------------------------------------------------
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            allowed_root TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            UNIQUE(name, allowed_root)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_root ON projects(allowed_root)")

    # ---- project_sources -------------------------------------------------
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            source_identifier TEXT NOT NULL,
            url TEXT,
            last_checked_utc TEXT,
            status TEXT,
            evidence_count INTEGER DEFAULT 0,
            notes TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            UNIQUE(project_id, source_type, source_identifier)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_projectsources_project ON project_sources(project_id)")

    # ---- discord_mappings ------------------------------------------------
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS discord_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            command_name TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            UNIQUE(project_id, guild_id, channel_id, command_name)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_discord_project ON discord_mappings(project_id)")

    # ---- authorized_users ------------------------------------------------
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS authorized_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_user_id INTEGER NOT NULL,
            project_id INTEGER,
            role TEXT NOT NULL DEFAULT 'member',
            granted_at_utc TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
            UNIQUE(discord_user_id, project_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_authorized_user ON authorized_users(discord_user_id)")

    # ---- notes -----------------------------------------------------------
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            discord_user_id INTEGER,
            content TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (discord_user_id) REFERENCES authorized_users(discord_user_id) ON DELETE SET NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notes_project ON notes(project_id)")

    # ---- milestones ------------------------------------------------------
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS milestones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            target_date_utc TEXT,
            completed_at_utc TEXT,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            UNIQUE(project_id, title)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_milestones_project ON milestones(project_id)")

    # ---- evidence --------------------------------------------------------
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            source_id INTEGER,
            title TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            retrieved_at_utc TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 1.0,
            claim TEXT,
            is_stale INTEGER NOT NULL DEFAULT 0,
            relevance_score REAL DEFAULT 0.0,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (source_id) REFERENCES project_sources(id) ON DELETE SET NULL,
            UNIQUE(project_id, source_id, title)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_project ON evidence(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_hash ON evidence(content_hash)")

    # ---- repository_snapshots --------------------------------------------
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS repository_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            git_commit_hash TEXT NOT NULL,
            git_branch TEXT NOT NULL,
            snapshot_time_utc TEXT NOT NULL,
            file_state_hash TEXT,
            status TEXT NOT NULL DEFAULT 'verified',
            notes TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reposnapshot_project ON repository_snapshots(project_id)")

    # ---- research_jobs ---------------------------------------------------
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS research_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            user_id INTEGER,
            question TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            started_at_utc TEXT NOT NULL,
            completed_at_utc TEXT,
            result_summary TEXT,
            model_used TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES authorized_users(discord_user_id) ON DELETE SET NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_research_project ON research_jobs(project_id)")

    # ---- research_sources ------------------------------------------------
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS research_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            research_job_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            canonical_url TEXT,
            source_type TEXT NOT NULL,
            retrieved_at_utc TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            FOREIGN KEY (research_job_id) REFERENCES research_jobs(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_resources_job ON research_sources(research_job_id)")

    # ---- research_reports ------------------------------------------------
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS research_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            research_job_id INTEGER NOT NULL,
            generated_at_utc TEXT NOT NULL,
            model_used TEXT,
            report_text TEXT NOT NULL,
            citation_count INTEGER DEFAULT 0,
            FOREIGN KEY (research_job_id) REFERENCES research_jobs(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_job ON research_reports(research_job_id)")

    # ---- scheduled_jobs --------------------------------------------------
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduled_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_type TEXT NOT NULL,
            project_id INTEGER,
            user_id INTEGER,
            next_run_utc TEXT NOT NULL,
            last_run_utc TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            args_hash TEXT,
            result TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
            FOREIGN KEY (user_id) REFERENCES authorized_users(discord_user_id) ON DELETE SET NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_next ON scheduled_jobs(next_run_utc)")

    # ---- health_snapshots ------------------------------------------------
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS health_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            checked_at_utc TEXT NOT NULL,
            status TEXT NOT NULL,
            details TEXT,
            git_head TEXT,
            git_dirty INTEGER NOT NULL DEFAULT 0,
            correlation_id TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_health_project ON health_snapshots(project_id)")

    # ---- agent_tasks -----------------------------------------------------
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            task_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            started_at_utc TEXT,
            completed_at_utc TEXT,
            result_text TEXT,
            error_text TEXT,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_project ON agent_tasks(project_id)")

    # ---- audit_events ----------------------------------------------------
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_discord_user_id INTEGER,
            action TEXT NOT NULL,
            result TEXT NOT NULL,
            outcome TEXT NOT NULL,
            timestamp_utc TEXT NOT NULL,
            correlation_id TEXT,
            project_id INTEGER,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
            FOREIGN KEY (actor_discord_user_id) REFERENCES authorized_users(discord_user_id) ON DELETE SET NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp_utc)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_events(actor_discord_user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_project ON audit_events(project_id)")

    conn.execute("COMMIT")
