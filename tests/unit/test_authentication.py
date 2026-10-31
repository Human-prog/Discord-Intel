"""Authentication context tests (Phase 5)."""

from __future__ import annotations

import pytest

from project_intelligence.security.authentication import (
    AuthContext,
    AuthError,
    authenticate_from_interaction,
    require_authentication,
)

USER = 111_111_111_111_111_111
GUILD = 222_222_222_222_222_222
CHANNEL = 333_333_333_333_333_333


def _context(**overrides) -> AuthContext:
    fields = {
        "discord_user_id": USER,
        "discord_guild_id": GUILD,
        "discord_channel_id": CHANNEL,
    }
    fields.update(overrides)
    return AuthContext(**fields)


def test_valid_interaction_builds_context() -> None:
    ctx = authenticate_from_interaction(
        interaction_user_id=USER,
        interaction_guild_id=GUILD,
        interaction_channel_id=CHANNEL,
    )
    assert ctx.discord_user_id == USER
    assert ctx.discord_guild_id == GUILD
    assert ctx.discord_channel_id == CHANNEL
    assert ctx.auth_via == "discord"


def test_numeric_strings_are_accepted() -> None:
    ctx = authenticate_from_interaction(
        interaction_user_id=str(USER),
        interaction_guild_id=str(GUILD),
        interaction_channel_id=str(CHANNEL),
    )
    assert ctx.discord_user_id == USER


@pytest.mark.parametrize("field", ["interaction_user_id", "interaction_guild_id", "interaction_channel_id"])
@pytest.mark.parametrize("value", [None, "", "not-a-number", 0, -1])
def test_invalid_snowflakes_are_rejected(field: str, value) -> None:
    kwargs = {
        "interaction_user_id": USER,
        "interaction_guild_id": GUILD,
        "interaction_channel_id": CHANNEL,
    }
    kwargs[field] = value
    with pytest.raises(AuthError):
        authenticate_from_interaction(**kwargs)


def test_is_owner_checks_configured_owner_ids(make_settings) -> None:
    settings = make_settings(discord_owner_user_ids=[USER])
    assert _context().is_owner(settings) is True
    assert _context(discord_user_id=USER + 1).is_owner(settings) is False


def test_empty_owner_list_means_no_discord_owner(make_settings) -> None:
    settings = make_settings(discord_owner_user_ids=[])
    assert _context().is_owner(settings) is False


def test_owner_session_is_always_owner(make_settings) -> None:
    settings = make_settings(discord_owner_user_ids=[])
    ctx = _context(discord_user_id=1, discord_guild_id=0, discord_channel_id=0, auth_via="owner_session")
    assert ctx.is_owner(settings) is True


def test_require_authentication_accepts_any_user_without_owner_list(make_settings) -> None:
    settings = make_settings(discord_owner_user_ids=[])
    require_authentication(_context(), settings=settings)  # no raise


def test_require_authentication_accepts_owner(make_settings) -> None:
    settings = make_settings(discord_owner_user_ids=[USER])
    require_authentication(_context(), settings=settings)  # no raise


def test_require_authentication_rejects_non_owner(make_settings) -> None:
    settings = make_settings(discord_owner_user_ids=[USER])
    with pytest.raises(AuthError, match="owner privileges"):
        require_authentication(_context(discord_user_id=USER + 1), settings=settings)


def test_require_authentication_accepts_owner_session(make_settings) -> None:
    settings = make_settings(discord_owner_user_ids=[USER])
    ctx = _context(discord_user_id=USER + 1, auth_via="owner_session")
    require_authentication(ctx, settings=settings)  # no raise
