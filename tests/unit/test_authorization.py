"""Centralized authorization tests (Phase 5)."""

from __future__ import annotations

import pytest

from project_intelligence.security.authentication import AuthContext
from project_intelligence.security.authorization import (
    AuthorizationError,
    make_checker,
)
from project_intelligence.storage import repositories as repo

USER = 111_111_111_111_111_111
OTHER_USER = 111_111_111_111_111_112
GUILD = 222_222_222_222_222_222
OTHER_GUILD = 222_222_222_222_222_223
CHANNEL = 333_333_333_333_333_333
OTHER_CHANNEL = 333_333_333_333_333_334


def _context(*, user: int = USER, guild: int = GUILD, channel: int = CHANNEL) -> AuthContext:
    return AuthContext(discord_user_id=user, discord_guild_id=guild, discord_channel_id=channel)


def _checker(settings, ctx: AuthContext | None = None):
    return make_checker(ctx or _context(), settings)


# ---------------------------------------------------------------------------
# Guild / channel scoping
# ---------------------------------------------------------------------------


def test_no_allowlists_allows_every_guild_and_channel(app_settings) -> None:
    _checker(app_settings).check_user_guild_channel()  # no raise


def test_empty_allowlists_bypass_the_check(app_settings) -> None:
    _checker(app_settings).check_user_guild_channel(required_guild_ids=[], required_channel_ids=[])


def test_guild_allowlist_denies_other_guilds(app_settings) -> None:
    with pytest.raises(AuthorizationError, match="guild"):
        _checker(app_settings).check_user_guild_channel(required_guild_ids=[OTHER_GUILD])


def test_guild_allowlist_allows_listed_guild(app_settings) -> None:
    _checker(app_settings).check_user_guild_channel(required_guild_ids=[GUILD])


def test_channel_allowlist_denies_other_channels(app_settings) -> None:
    with pytest.raises(AuthorizationError, match="channel"):
        _checker(app_settings).check_user_guild_channel(required_channel_ids=[OTHER_CHANNEL])


def test_channel_allowlist_allows_listed_channel(app_settings) -> None:
    _checker(app_settings).check_user_guild_channel(required_channel_ids=[CHANNEL])


# ---------------------------------------------------------------------------
# Project access
# ---------------------------------------------------------------------------


def test_owner_session_has_access_to_any_project(app_settings) -> None:
    owner_ctx = AuthContext(
        discord_user_id=USER,
        discord_guild_id=0,
        discord_channel_id=0,
        auth_via="owner_session",
    )
    make_checker(owner_ctx, app_settings).check_project_access(999_999)  # no raise


def test_configured_owner_has_access_to_any_project(app_settings) -> None:
    owner = app_settings.discord_owner_user_ids[0]
    _checker(app_settings, _context(user=owner)).check_project_access(999_999)


def test_unknown_user_is_denied_project_access(db, app_settings) -> None:
    project = repo.upsert_project(db, "Alpha", None, "/srv/alpha")
    with pytest.raises(AuthorizationError, match="not authorized"):
        _checker(app_settings, _context(user=OTHER_USER)).check_project_access(project.id)


def test_authorized_user_gets_project_access(db, app_settings) -> None:
    project = repo.upsert_project(db, "Alpha", None, "/srv/alpha")
    repo.upsert_authorized_user(db, USER, project.id, role="member")
    _checker(app_settings).check_project_access(project.id)  # no raise


def test_authorized_user_is_scoped_to_one_project(db, app_settings) -> None:
    project = repo.upsert_project(db, "Alpha", None, "/srv/alpha")
    other = repo.upsert_project(db, "Beta", None, "/srv/beta")
    repo.upsert_authorized_user(db, USER, project.id)

    _checker(app_settings).check_project_access(project.id)
    with pytest.raises(AuthorizationError):
        _checker(app_settings).check_project_access(other.id)


def test_owner_or_project_allows_owner(app_settings) -> None:
    owner = app_settings.discord_owner_user_ids[0]
    _checker(app_settings, _context(user=owner)).check_owner_or_project(999_999)


# ---------------------------------------------------------------------------
# Command mapping
# ---------------------------------------------------------------------------


def test_command_mapping_is_required(db, app_settings) -> None:
    project = repo.upsert_project(db, "Alpha", None, "/srv/alpha")
    with pytest.raises(AuthorizationError, match="not mapped"):
        _checker(app_settings).check_command_mapped(project.id, "next")


def test_mapped_command_is_allowed(db, app_settings) -> None:
    project = repo.upsert_project(db, "Alpha", None, "/srv/alpha")
    repo.upsert_discord_mapping(db, project.id, GUILD, CHANNEL, "next")
    _checker(app_settings).check_command_mapped(project.id, "next")  # no raise


def test_mapping_is_scoped_to_guild_and_channel(db, app_settings) -> None:
    project = repo.upsert_project(db, "Alpha", None, "/srv/alpha")
    repo.upsert_discord_mapping(db, project.id, GUILD, CHANNEL, "next")

    with pytest.raises(AuthorizationError):
        _checker(app_settings, _context(guild=OTHER_GUILD)).check_command_mapped(project.id, "next")
    with pytest.raises(AuthorizationError):
        _checker(app_settings, _context(channel=OTHER_CHANNEL)).check_command_mapped(
            project.id, "next"
        )


def test_project_and_command_requires_both(db, app_settings) -> None:
    project = repo.upsert_project(db, "Alpha", None, "/srv/alpha")
    repo.upsert_authorized_user(db, USER, project.id)

    with pytest.raises(AuthorizationError, match="not mapped"):
        _checker(app_settings).check_project_and_command(project.id, "next")

    repo.upsert_discord_mapping(db, project.id, GUILD, CHANNEL, "next")
    _checker(app_settings).check_project_and_command(project.id, "next")  # no raise
