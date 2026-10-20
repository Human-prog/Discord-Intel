"""Centralized authentication interface (Phase 5).

Provides AuthContext and functions to extract, validate, and require
Discord identity from interaction contexts.  Fail-closed: raises AuthError
when identity information is missing, malformed, or ambiguous.

All Discord identity values are numeric snowflakes (positive integers).
No client-supplied values are trusted without server-side validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import Settings


class AuthError(Exception):
    """Raised when authentication cannot succeed. Message never contains secrets."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class AuthContext:
    """Immutable context carrying validated Discord identity.

    Invariants: if the context was constructed successfully, all IDs are
    positive integers.  Missing or invalid IDs are never represented - the
    constructor raises AuthError instead.
    """

    discord_user_id: int
    """The Discord user ID that issued the command."""

    discord_guild_id: int
    """The guild (server) where the command was invoked."""

    discord_channel_id: int
    """The channel within the guild where the command was invoked."""

    auth_via: str = "discord"
    """Where the context came from: 'discord' (interaction) or 'owner_session'."""

    def is_owner(self, settings: Settings) -> bool:
        """True if this is an owner session or the user is a configured owner."""
        if self.auth_via == "owner_session":
            return True
        return self.discord_user_id in settings.discord_owner_user_ids


def _snowflake(value: Any, field_name: str) -> int:
    """Validate that *value* is a positive integer (Discord snowflake).

    Raises AuthError if the value is not a valid snowflake.
    """
    try:
        iv = int(value)
    except (TypeError, ValueError, AttributeError):
        raise AuthError(f"Invalid {field_name}: must be a positive integer snowflake") from None
    if iv < 1:
        raise AuthError(f"Invalid {field_name}: Discord IDs must be positive (got {iv})") from None
    return iv


def authenticate_from_interaction(
    *,
    interaction_user_id: Any,
    interaction_guild_id: Any,
    interaction_channel_id: Any,
) -> AuthContext:
    """Build an AuthContext from a Discord interaction event payload.

    This is the single entry point for turning raw interaction JSON into
    a validated authentication context.  All three IDs must be present and
    valid; otherwise AuthError is raised.
    """
    user = _snowflake(interaction_user_id, "user_id")
    guild = _snowflake(interaction_guild_id, "guild_id")
    channel = _snowflake(interaction_channel_id, "channel_id")
    return AuthContext(discord_user_id=user, discord_guild_id=guild, discord_channel_id=channel)


def require_authentication(auth_ctx: AuthContext, *, settings: Settings) -> None:
    """Fail-closed: raise AuthError if the context does not represent a
    configured owner when owner-only operation is required.

    By default (non-production or when owner IDs are empty) any authenticated
    user is accepted.  Production mode with owner IDs configured requires
    explicit owner membership.
    """
    # If no owner IDs are configured, any authenticated user is accepted.
    if not settings.discord_owner_user_ids:
        return

    # In production mode, only the configured owner may proceed.
    if auth_ctx.is_owner(settings):
        return

    raise AuthError(
        "Authorization failed: this operation requires owner privileges; "
        "your user ID is not in the owner allowlist."
    )
