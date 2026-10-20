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
        (commands.note_command.callback, ("note",)),
        (commands.health_command.callback, ()),
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
