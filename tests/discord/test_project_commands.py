"""Offline tests for /next, /roadmap, /blocker, /connect-project, /note, /health."""

from __future__ import annotations

import asyncio
from pathlib import Path

from project_intelligence.discord.commands import project_commands as commands
from project_intelligence.health.health_engine import store_health_snapshot
from project_intelligence.storage import repositories as repo

from .helpers import CHANNEL_ID, GUILD_ID, OTHER_USER_ID, OWNER_ID, FakeInteraction


def _run(coro):
    return asyncio.run(coro)


def _project(db, settings=None, name: str = "Alpha"):
    root = Path("/srv/alpha")
    if settings is not None:
        root = settings.project_allowed_roots[0] / name.lower()
        root.mkdir(parents=True, exist_ok=True)
    return repo.upsert_project(db, name, None, str(root))


def _map(db, project_id: int, command_name: str) -> None:
    repo.upsert_discord_mapping(db, project_id, GUILD_ID, CHANNEL_ID, command_name)


def _interaction(settings, **kwargs) -> FakeInteraction:
    return FakeInteraction(settings, **kwargs)


# ---------------------------------------------------------------------------
# Authentication / authorization
# ---------------------------------------------------------------------------


def test_commands_require_an_auth_context(app_settings) -> None:
    for callback, args in (
        (commands.next_command.callback, ()),
        (commands.roadmap_command.callback, ()),
        (commands.blocker_command.callback, ()),
        (commands.connect_project_command.callback, (1,)),
        (commands.create_project_command.callback, ("Alpha", "/srv/alpha")),
        (commands.note_command.callback, ("note",)),
        (commands.health_command.callback, ()),
        (commands.research_command.callback, ("question",)),
    ):
        interaction = _interaction(app_settings, has_auth=False)
        _run(callback(interaction, *args))
        assert interaction.last_message == "Authentication required."


def test_commands_require_settings_on_the_client(app_settings) -> None:
    interaction = _interaction(app_settings)
    interaction.client = type("Client", (), {"settings": None})()
    _run(commands.note_command.callback(interaction, "note"))
    assert interaction.last_message == "Authentication required."


def test_connect_project_is_owner_only(db, app_settings) -> None:
    project = _project(db, app_settings)
    interaction = _interaction(app_settings, user_id=OTHER_USER_ID, auth_via="discord")

    _run(commands.connect_project_command.callback(interaction, project.id))

    assert "Only owners" in interaction.last_message
    assert repo.get_mapped_project_id(db, GUILD_ID, CHANNEL_ID, "note") is None


# ---------------------------------------------------------------------------
# /connect-project
# ---------------------------------------------------------------------------


def test_connect_project_maps_all_commands(db, app_settings) -> None:
    project = _project(db, app_settings)
    interaction = _interaction(app_settings)

    _run(commands.connect_project_command.callback(interaction, project.id))

    assert "connected" in interaction.last_message
    for name in commands.MAPPED_COMMANDS:
        assert repo.get_mapped_project_id(db, GUILD_ID, CHANNEL_ID, name) == project.id
    assert commands.resolve_project_id(GUILD_ID, CHANNEL_ID, "note") == project.id


def test_connect_project_rejects_unknown_project(db, app_settings) -> None:
    interaction = _interaction(app_settings)
    _run(commands.connect_project_command.callback(interaction, 999))
    assert "was not found" in interaction.last_message


def test_connect_project_rejects_roots_outside_the_allowlist(
    db, app_settings, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    project = repo.upsert_project(db, "Outside", None, str(outside))
    interaction = _interaction(app_settings)

    _run(commands.connect_project_command.callback(interaction, project.id))

    assert "outside the configured PROJECT_ALLOWED_ROOTS" in interaction.last_message
    assert repo.get_mapped_project_id(db, GUILD_ID, CHANNEL_ID, "note") is None


def test_connect_project_fails_closed_without_allowed_roots(db, make_settings) -> None:
    project = _project(db)
    interaction = _interaction(make_settings(project_allowed_roots=[]))
    _run(commands.connect_project_command.callback(interaction, project.id))
    assert "outside the configured PROJECT_ALLOWED_ROOTS" in interaction.last_message


def test_root_is_allowed_helper(app_settings, tmp_path: Path) -> None:
    allowed = app_settings.project_allowed_roots[0]
    assert commands.root_is_allowed(str(allowed / "child"), app_settings) is True
    assert commands.root_is_allowed(str(allowed), app_settings) is True
    assert commands.root_is_allowed(str(tmp_path / "elsewhere"), app_settings) is False
    assert commands.root_is_allowed("relative/path", app_settings) is False


def test_root_is_allowed_handles_resolve_errors(make_settings, monkeypatch, tmp_path: Path) -> None:
    original = Path.resolve
    bad = tmp_path / "bad"

    def resolve(self, *args, **kwargs):
        if self == bad:
            raise OSError("broken path")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    settings = make_settings(project_allowed_roots=[bad])
    assert commands.root_is_allowed(str(bad), settings) is False
    assert commands.root_is_allowed(str(tmp_path / "ok"), settings) is False


# ---------------------------------------------------------------------------
# /create-project
# ---------------------------------------------------------------------------


def _allowed_root(app_settings, name: str = "alpha") -> Path:
    root = app_settings.project_allowed_roots[0] / name
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_create_project_is_owner_only(db, app_settings) -> None:
    interaction = _interaction(app_settings, user_id=OTHER_USER_ID)

    _run(
        commands.create_project_command.callback(
            interaction, "Alpha", str(_allowed_root(app_settings))
        )
    )

    assert "Only owners" in interaction.last_message
    assert repo.list_projects(db) == []


def test_create_project_rejects_relative_root(db, app_settings) -> None:
    interaction = _interaction(app_settings)

    _run(commands.create_project_command.callback(interaction, "Alpha", "relative/path"))

    assert "must be an absolute path" in interaction.last_message
    assert repo.list_projects(db) == []


def test_create_project_rejects_missing_root(db, app_settings, tmp_path: Path) -> None:
    interaction = _interaction(app_settings)

    _run(
        commands.create_project_command.callback(
            interaction, "Alpha", str(app_settings.project_allowed_roots[0] / "missing")
        )
    )

    assert "was not found" in interaction.last_message
    assert repo.list_projects(db) == []


def test_create_project_rejects_file_root(db, app_settings) -> None:
    file_root = app_settings.project_allowed_roots[0] / "not-a-dir"
    file_root.write_text("x", encoding="utf-8")
    interaction = _interaction(app_settings)

    _run(commands.create_project_command.callback(interaction, "Alpha", str(file_root)))

    assert "not a directory" in interaction.last_message
    assert repo.list_projects(db) == []


def test_create_project_rejects_root_outside_the_allowlist(
    db, app_settings, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    interaction = _interaction(app_settings)

    _run(commands.create_project_command.callback(interaction, "Outside", str(outside)))

    assert "outside the configured PROJECT_ALLOWED_ROOTS" in interaction.last_message
    assert repo.list_projects(db) == []


def test_create_project_registers_and_maps(db, app_settings) -> None:
    root = _allowed_root(app_settings)
    interaction = _interaction(app_settings)

    _run(
        commands.create_project_command.callback(
            interaction, "  Alpha  ", str(root), "  sample project  "
        )
    )

    assert "created and connected" in interaction.last_message
    project = repo.get_project_by_root(db, str(root))
    assert project is not None
    assert project.name == "Alpha"
    assert project.description == "sample project"
    for name in commands.MAPPED_COMMANDS:
        assert repo.get_mapped_project_id(db, GUILD_ID, CHANNEL_ID, name) == project.id


def test_create_project_connects_an_existing_root(db, app_settings) -> None:
    root = _allowed_root(app_settings)
    interaction = _interaction(app_settings)

    _run(commands.create_project_command.callback(interaction, "Alpha", str(root)))
    _run(commands.create_project_command.callback(interaction, "Renamed", str(root)))

    assert "already exists; connected" in interaction.last_message
    assert len(repo.list_projects(db)) == 1


def test_create_project_rejects_an_overlong_name(db, app_settings) -> None:
    interaction = _interaction(app_settings)

    _run(
        commands.create_project_command.callback(
            interaction, "x" * 201, str(_allowed_root(app_settings))
        )
    )

    assert "between 1 and 200 characters" in interaction.last_message
    assert repo.list_projects(db) == []


# ---------------------------------------------------------------------------
# /note
# ---------------------------------------------------------------------------


def test_note_requires_a_mapping(db, app_settings) -> None:
    project = _project(db, app_settings)
    interaction = _interaction(app_settings)
    _run(commands.note_command.callback(interaction, "hello"))

    assert "No project is mapped" in interaction.last_message
    assert repo.list_notes_for_project(db, project.id) == []


def test_note_is_persisted(db, app_settings) -> None:
    project = _project(db, app_settings)
    _map(db, project.id, "note")
    interaction = _interaction(app_settings)

    _run(commands.note_command.callback(interaction, "  remember this  "))

    assert "Note saved" in interaction.last_message
    notes = repo.list_notes_for_project(db, project.id)
    assert len(notes) == 1
    assert notes[0].content == "remember this"
    assert notes[0].discord_user_id == OWNER_ID


def test_empty_note_is_rejected(db, app_settings) -> None:
    project = _project(db, app_settings)
    _map(db, project.id, "note")
    interaction = _interaction(app_settings)

    _run(commands.note_command.callback(interaction, "   "))

    assert "cannot be empty" in interaction.last_message
    assert repo.list_notes_for_project(db, project.id) == []


def test_note_requires_project_access(db, app_settings) -> None:
    project = _project(db, app_settings)
    _map(db, project.id, "note")
    interaction = _interaction(app_settings, user_id=OTHER_USER_ID)

    _run(commands.note_command.callback(interaction, "hello"))

    assert "not authorized" in interaction.last_message
    assert repo.list_notes_for_project(db, project.id) == []


# ---------------------------------------------------------------------------
# /roadmap
# ---------------------------------------------------------------------------


def test_roadmap_lists_milestones(db, app_settings) -> None:
    project = _project(db, app_settings)
    _map(db, project.id, "roadmap")
    repo.upsert_milestone(db, project.id, "Ship v1", None, "in_progress", "2026-12-01")
    interaction = _interaction(app_settings)

    _run(commands.roadmap_command.callback(interaction))

    message = interaction.last_message
    assert "Project Roadmap" in message
    assert "Ship v1" in message
    assert "in_progress" in message
    assert "target 2026-12-01" in message


def test_roadmap_without_milestones(db, app_settings) -> None:
    project = _project(db, app_settings)
    _map(db, project.id, "roadmap")
    interaction = _interaction(app_settings)

    _run(commands.roadmap_command.callback(interaction))
    assert "No milestones recorded" in interaction.last_message


def test_roadmap_requires_a_mapping(db, app_settings) -> None:
    interaction = _interaction(app_settings)
    _run(commands.roadmap_command.callback(interaction))
    assert "No project is mapped" in interaction.last_message


# ---------------------------------------------------------------------------
# /next, /blocker
# ---------------------------------------------------------------------------


def test_next_explains_missing_mapping(db, app_settings) -> None:
    interaction = _interaction(app_settings)
    _run(commands.next_command.callback(interaction))
    assert "No project is mapped" in interaction.last_message


def test_next_acknowledges_mapped_project(db, app_settings) -> None:
    project = _project(db, app_settings)
    _map(db, project.id, "next")
    interaction = _interaction(app_settings)
    _run(commands.next_command.callback(interaction))
    assert "No suggested actions" in interaction.last_message


def test_blocker_guides_toward_notes(app_settings) -> None:
    interaction = _interaction(app_settings)
    _run(commands.blocker_command.callback(interaction))
    assert "/note" in interaction.last_message


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


def test_health_runs_and_stores_a_snapshot(db, app_settings) -> None:
    project = _project(db, app_settings)
    _map(db, project.id, "health")
    interaction = _interaction(app_settings)

    _run(commands.health_command.callback(interaction))

    assert "Project Health" in interaction.last_message
    latest = repo.get_latest_health_snapshot(db, project.id)
    assert latest is not None
    assert latest[0] in {"healthy", "stale", "unhealthy", "unknown"}


def test_health_reports_rate_limiting(db, app_settings, monkeypatch) -> None:
    project = _project(db, app_settings)
    _map(db, project.id, "health")

    class _Limited:
        @staticmethod
        def check_health_per_hour():
            return True, 10_000_000_000.0

    monkeypatch.setattr(commands, "rate_limiter", _Limited())
    interaction = _interaction(app_settings)
    _run(commands.health_command.callback(interaction))
    assert "rate limited" in interaction.last_message


def test_health_requires_a_mapping(db, app_settings) -> None:
    interaction = _interaction(app_settings)
    _run(commands.health_command.callback(interaction))
    assert "No project is mapped" in interaction.last_message


def test_health_requires_project_access(db, app_settings) -> None:
    project = _project(db, app_settings)
    _map(db, project.id, "health")
    interaction = _interaction(app_settings, user_id=OTHER_USER_ID)
    _run(commands.health_command.callback(interaction))
    assert "not authorized" in interaction.last_message


def test_stored_health_snapshot_is_reported(db, app_settings) -> None:
    project = _project(db, app_settings)
    _map(db, project.id, "health")
    store_health_snapshot(project.id, "healthy", details={"root_exists": True})
    interaction = _interaction(app_settings)

    _run(commands.health_command.callback(interaction))

    # /health performs a fresh check, so the pre-seeded snapshot is superseded.
    latest = repo.get_latest_health_snapshot(db, project.id)
    assert latest is not None
    assert latest[0] in interaction.last_message
    assert latest[1] in interaction.last_message


# ---------------------------------------------------------------------------
# /research
# ---------------------------------------------------------------------------


def _allow_research(monkeypatch) -> None:
    class _Unlimited:
        @staticmethod
        def check_research_per_user(user_id):
            return False, 0.0

    monkeypatch.setattr(commands, "rate_limiter", _Unlimited())


def _fake_research(monkeypatch, *, result=None, error=None, captured=None):
    from types import SimpleNamespace

    def fake(question, *, project_id, user_id, scope, settings):
        if captured is not None:
            captured.update(
                question=question,
                project_id=project_id,
                user_id=user_id,
                scope=scope,
                settings=settings,
            )
        if error is not None:
            raise error
        return result or SimpleNamespace(
            job_id=7,
            status="completed",
            scope=scope,
            provider=None,
            report="# Report\n\nAnswer",
            source_count=2,
            local_count=1,
            web_count=1,
            error=None,
        )

    monkeypatch.setattr(commands, "run_research", fake)


def test_research_requires_auth_and_settings(app_settings) -> None:
    interaction = _interaction(app_settings, has_auth=False)
    _run(commands.research_command.callback(interaction, "question"))
    assert interaction.last_message == "Authentication required."

    interaction = _interaction(app_settings)
    interaction.client = type("Client", (), {"settings": None})()
    _run(commands.research_command.callback(interaction, "question"))
    assert interaction.last_message == "Authentication required."


def test_research_rejects_invalid_scope_empty_and_overlong_question(
    db, app_settings, monkeypatch
) -> None:
    _allow_research(monkeypatch)
    interaction = _interaction(app_settings)

    _run(commands.research_command.callback(interaction, "question", "everything"))
    assert "Scope must be one of" in interaction.last_message

    _run(commands.research_command.callback(interaction, "   "))
    assert "cannot be empty" in interaction.last_message

    _run(commands.research_command.callback(interaction, "x" * 1001))
    assert "1000 characters" in interaction.last_message


def test_research_rate_limits(db, app_settings, monkeypatch) -> None:
    class _Limited:
        @staticmethod
        def check_research_per_user(user_id):
            return True, 10_000_000_000.0

    monkeypatch.setattr(commands, "rate_limiter", _Limited())
    interaction = _interaction(app_settings)
    _run(commands.research_command.callback(interaction, "question"))
    assert "rate limited" in interaction.last_message


def test_research_rejects_unknown_explicit_project(db, app_settings, monkeypatch) -> None:
    _allow_research(monkeypatch)
    interaction = _interaction(app_settings)
    _run(commands.research_command.callback(interaction, "question", "local", 999))
    assert "was not found" in interaction.last_message


def test_research_requires_project_access(db, app_settings, monkeypatch) -> None:
    _allow_research(monkeypatch)
    project = _project(db, app_settings)
    _map(db, project.id, "note")
    interaction = _interaction(app_settings, user_id=OTHER_USER_ID)
    _run(commands.research_command.callback(interaction, "question", "local", project.id))
    assert "not authorized" in interaction.last_message


def test_research_uses_the_channel_project_and_returns_a_report(
    db, app_settings, monkeypatch
) -> None:
    _allow_research(monkeypatch)
    project = _project(db, app_settings)
    _map(db, project.id, "note")
    captured = {}
    _fake_research(monkeypatch, captured=captured)
    interaction = _interaction(app_settings)

    _run(commands.research_command.callback(interaction, "  how   does research work?  ", "local"))

    assert interaction.response.deferred is True
    assert captured["question"] == "how does research work?"
    assert captured["project_id"] == project.id
    assert captured["scope"] == "local"
    assert captured["user_id"] == OWNER_ID
    assert "Research #7" in interaction.last_message
    assert "1 local" in interaction.last_message
    assert "1 web" in interaction.last_message
    assert "Answer" in interaction.last_message
    assert interaction.followup.messages[0][1] is True


def test_research_without_a_channel_project_passes_none(db, app_settings, monkeypatch) -> None:
    _allow_research(monkeypatch)
    captured = {}
    _fake_research(monkeypatch, captured=captured)
    interaction = _interaction(app_settings)
    _run(commands.research_command.callback(interaction, "question", "web", None))
    assert captured["project_id"] is None


def test_research_truncates_long_reports_and_links_the_dashboard(
    db, app_settings, monkeypatch, make_settings
) -> None:
    from types import SimpleNamespace

    _allow_research(monkeypatch)
    settings = make_settings(
        dashboard_public_url="https://desk.example/",
        discord_owner_user_ids=[OWNER_ID],
    )
    result = SimpleNamespace(
        job_id=42,
        status="completed",
        scope="both",
        provider="tavily",
        report="x" * 2000,
        source_count=3,
        local_count=1,
        web_count=2,
        error=None,
    )
    _fake_research(monkeypatch, result=result)
    interaction = _interaction(settings)
    _run(commands.research_command.callback(interaction, "question", "both", None))
    message = interaction.last_message
    assert "Full report saved in the dashboard." in message
    assert "https://desk.example/#research-42" in message
    assert len(message) < 2000


def test_research_failures_are_reported(db, app_settings, monkeypatch) -> None:
    from types import SimpleNamespace

    _allow_research(monkeypatch)
    _fake_research(monkeypatch, error=commands.ResearchError("provider down"))
    interaction = _interaction(app_settings)
    _run(commands.research_command.callback(interaction, "question"))
    assert "Research failed" in interaction.last_message
    assert "provider down" in interaction.last_message

    _fake_research(
        monkeypatch,
        result=SimpleNamespace(
            job_id=8,
            status="failed",
            scope="web",
            provider="tavily",
            report="",
            source_count=0,
            local_count=0,
            web_count=0,
            error="Not configured",
        ),
    )
    interaction = _interaction(app_settings)
    _run(commands.research_command.callback(interaction, "question", "web"))
    assert "Research failed" in interaction.last_message
    assert "Not configured" in interaction.last_message


def test_research_value_error_is_reported(db, app_settings, monkeypatch) -> None:
    _allow_research(monkeypatch)
    _fake_research(monkeypatch, error=ValueError("bad question"))
    interaction = _interaction(app_settings)
    _run(commands.research_command.callback(interaction, "question"))
    assert "bad question" in interaction.last_message


def test_research_rejects_a_disallowed_guild(make_settings) -> None:
    settings = make_settings(
        discord_allowed_guild_ids=[999],
        discord_owner_user_ids=[OWNER_ID],
    )
    interaction = _interaction(settings)
    _run(commands.research_command.callback(interaction, "question"))
    assert "not authorized" in interaction.last_message.lower()


def test_existing_commands_reject_a_disallowed_guild(make_settings) -> None:
    settings = make_settings(
        discord_allowed_guild_ids=[999],
        discord_owner_user_ids=[OWNER_ID],
    )
    for callback, args in (
        (commands.next_command.callback, ()),
        (commands.roadmap_command.callback, ()),
        (commands.blocker_command.callback, ()),
    ):
        interaction = _interaction(settings)
        _run(callback(interaction, *args))
        assert "not authorized" in interaction.last_message.lower()
